/*
 * Emulated thread-local storage for Clang on AROS (-femulated-tls).
 *
 * AROS programs have no thread-local segment, so `thread_local` and
 * `__thread` variables are compiled as calls to __emutls_get_address(), which
 * the toolchain's runtime does not have. This is that function: every
 * variable gets a number on first use, and every task keeps its own copies in
 * a table held in a task storage slot (task.resource), so a new task at the
 * address of an ended one starts with fresh values.
 *
 * The copies of a task that ends are not freed until the program ends (AROS
 * has no hook for the end of a task that this code could use).
 *
 * __cxa_thread_atexit(), which C++ calls for a thread_local object with a
 * destructor, is here too, since the C++ runtime for AROS leaves it out:
 * destructors registered by the program's own task run when the program
 * ends, newest first; those registered by other tasks never run.
 *
 * This file is in the public domain.
 */

#include <aros/symbolsets.h>
#include <exec/types.h>
#include <exec/semaphores.h>
#include <exec/tasks.h>
#include <proto/exec.h>
#include <proto/task.h>

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* The object the compiler emits for each variable (GCC and Clang agree). */
struct emutls_object
{
	size_t size;
	size_t align;
	union
	{
		uintptr_t index;
		void *address;
	} loc;
	void *templ;
};

struct emutls_table
{
	size_t count;
	void *copy[1];
};

static struct SignalSemaphore lock;
/* task.resource; the calls below read it through a local TaskResBase. */
static APTR taskres;
static LONG slot;
static uintptr_t variables;

/* Before main() and before any other task of the program exists. */
static int emutls_init(void)
{
	APTR TaskResBase;

	InitSemaphore(&lock);
	TaskResBase = taskres = OpenResource((CONST_STRPTR) "task.resource");
	if (TaskResBase)
		slot = AllocTaskStorageSlot();
	return slot != 0;
}

struct emutls_dtor
{
	struct emutls_dtor *next;
	struct Task *task;
	void (*function)(void *);
	void *object;
};

static struct emutls_dtor *dtors;

int __cxa_thread_atexit(void (*function)(void *), void *object, void *dso)
{
	struct emutls_dtor *d = (struct emutls_dtor *) malloc(sizeof(*d));

	(void) dso;
	if (!d)
		return -1;
	d->task = FindTask(NULL);
	d->function = function;
	d->object = object;
	ObtainSemaphore(&lock);
	d->next = dtors;
	dtors = d;
	ReleaseSemaphore(&lock);
	return 0;
}

static void emutls_exit(void)
{
	APTR TaskResBase = taskres;
	struct Task *me = FindTask(NULL);
	struct emutls_dtor *d;

	/* The list is newest first. A destructor may register another. */
	for (;;)
	{
		struct emutls_dtor **link;

		ObtainSemaphore(&lock);
		for (link = &dtors; (d = *link) && d->task != me; link = &d->next)
			;
		if (d)
			*link = d->next;
		ReleaseSemaphore(&lock);
		if (!d)
			break;
		d->function(d->object);
		free(d);
	}

	if (slot)
	{
		/* A freed slot keeps its value in the tasks that used it. */
		SetTaskStorageSlot(slot, 0);
		FreeTaskStorageSlot(slot);
		slot = 0;
	}
}

ADD2INIT(emutls_init, -20);
ADD2EXIT(emutls_exit, -20);

static void *emutls_copy(const struct emutls_object *obj)
{
	size_t align = obj->align < sizeof(void *) ? sizeof(void *) : obj->align;
	char *raw = (char *) malloc(obj->size + align + sizeof(void *));
	char *p;

	if (!raw)
		abort();

	p = (char *) (((uintptr_t) raw + sizeof(void *) + align - 1) & ~(uintptr_t) (align - 1));
	((void **) p)[-1] = raw;
	if (obj->templ)
		memcpy(p, obj->templ, obj->size);
	else
		memset(p, 0, obj->size);
	return p;
}

void *__emutls_get_address(struct emutls_object *obj)
{
	uintptr_t index = __atomic_load_n(&obj->loc.index, __ATOMIC_ACQUIRE);
	struct emutls_table *table;
	APTR TaskResBase = taskres;

	if (!index)
	{
		ObtainSemaphore(&lock);
		index = obj->loc.index;
		if (!index)
		{
			index = ++variables;
			__atomic_store_n(&obj->loc.index, index, __ATOMIC_RELEASE);
		}
		ReleaseSemaphore(&lock);
	}

	table = (struct emutls_table *) GetTaskStorageSlot(slot);
	if (!table || table->count < index)
	{
		size_t count = index + 16;
		struct emutls_table *grown = (struct emutls_table *) calloc(1, sizeof(*grown) + count * sizeof(void *));

		if (!grown)
			abort();
		if (table)
		{
			memcpy(grown->copy, table->copy, table->count * sizeof(void *));
			free(table);
		}
		grown->count = count;
		if (!SetTaskStorageSlot(slot, (IPTR) grown))
			abort();
		table = grown;
	}

	if (!table->copy[index - 1])
		table->copy[index - 1] = emutls_copy(obj);
	return table->copy[index - 1];
}
