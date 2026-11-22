-- Diagnostic for stalls in a LOVE game.
--
-- Put this file beside the game's main.lua and add as the first line of main.lua:
--     require "arosdiag"
-- Play until the stall has happened a few times, quit, and send the log:
-- RAM:lovediag.log (or the file named in the environment variable LOVEDIAG).
--
-- Every 10 seconds one line is written: frames, the slowest frame, and what
-- LuaJIT's compiler did (traces finished/started, flushes of all compiled
-- code, aborts by error number; 27 = no memory for machine code). Every frame
-- longer than half a second gets its own line with the time spent in the
-- game's update, in its draw, in showing the frame, in reading events and in
-- sleeping. Time missing from that sum was spent outside the game's own code:
-- the game was not running.
local path = os.getenv("LOVEDIAG") or "RAM:lovediag.log"
local limit = tonumber(os.getenv("LOVEDIAGQUIT") or "0")

local function out(s)
  local f = io.open(path, "a")
  if f then f:write(s, "\n"); f:close() end
end

local started, stopped, flushes, aborts = 0, 0, 0, {}
if jit and jit.attach then
  jit.attach(function(what, tr, func, pc, code)
    if what == "start" then started = started + 1
    elseif what == "stop" then stopped = stopped + 1
    elseif what == "flush" then flushes = flushes + 1
    elseif what == "abort" then aborts[code] = (aborts[code] or 0) + 1 end
  end, "trace")
end

local function state()
  local t = {}
  for code, n in pairs(aborts) do t[#t + 1] = code .. "x" .. n end
  table.sort(t)
  return ("traces %d/%d flushes %d aborts [%s] lua %.0f KB"):format(
    stopped, started, flushes, table.concat(t, " "), collectgarbage("count"))
end

local clock = love.timer.getTime
local spent = { update = 0, draw = 0, present = 0, events = 0, sleep = 0 }

-- Time a function of a table under a name; the game may define it later.
local wrapped = {}
local function wrap(tbl, key, name)
  local f = tbl[key]
  if type(f) ~= "function" or wrapped[f] then return end
  local w = function(...)
    local a = clock()
    local r1, r2, r3 = f(...)
    spent[name] = spent[name] + (clock() - a)
    return r1, r2, r3
  end
  wrapped[w] = true
  tbl[key] = w
end

local step = love.timer.step
local t0, last, frames, worst = clock(), clock(), 0, 0
out(("start: %s, jit %s, %s"):format(os.date(), tostring(jit and jit.status()), state()))

love.timer.step = function()
  local dt = step()
  local now = clock()
  frames = frames + 1
  if dt > worst then worst = dt end
  if dt > 0.5 then
    out(("t %7.1f  LONG FRAME %.2f s: update %.2f draw %.2f present %.2f events %.2f sleep %.2f  %s"):format(
      now - t0, dt, spent.update, spent.draw, spent.present, spent.events, spent.sleep, state()))
  end
  if now - last >= 10 then
    out(("t %7.1f  %d frames, slowest %.2f s  %s"):format(now - t0, frames, worst, state()))
    last, frames, worst = now, 0, 0
  end
  for k in pairs(spent) do spent[k] = 0 end
  wrap(love, "update", "update")
  wrap(love, "draw", "draw")
  if love.graphics then wrap(love.graphics, "present", "present") end
  if love.event then wrap(love.event, "pump", "events") end
  wrap(love.timer, "sleep", "sleep")
  if limit > 0 and now - t0 > limit then out("quit"); love.event.quit() end
  return dt
end
