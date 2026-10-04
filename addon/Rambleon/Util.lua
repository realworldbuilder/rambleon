-- Rambleon: shared helpers. Keep everything here free of game-state side effects.
local ADDON, ns = ...

ns.ADDON_NAME = ADDON
ns.SCHEMA_VERSION = 1
ns.flavorHint = ns.flavorHint or "unknown"
ns.failedEvents = {}
ns.warnings = {}
ns.debugEnabled = false
ns.NOTE_MAX = 500               -- characters kept of a note

do
  local version
  if C_AddOns and C_AddOns.GetAddOnMetadata then
    version = C_AddOns.GetAddOnMetadata(ADDON, "Version")
  elseif GetAddOnMetadata then
    version = GetAddOnMetadata(ADDON, "Version")
  end
  ns.VERSION = version or "dev"
end

local COLOR = "|cffd9a760"

function ns.Print(msg)
  local line = COLOR .. "Rambleon|r: " .. tostring(msg)
  if DEFAULT_CHAT_FRAME and DEFAULT_CHAT_FRAME.AddMessage then
    DEFAULT_CHAT_FRAME:AddMessage(line)
  else
    print(line)
  end
end

function ns.Debug(msg)
  if ns.debugEnabled then
    ns.Print("|cff999999" .. tostring(msg) .. "|r")
  end
end

function ns.Warn(msg)
  table.insert(ns.warnings, tostring(msg))
  if #ns.warnings > 50 then table.remove(ns.warnings, 1) end
  ns.Debug("warning: " .. tostring(msg))
end

-- Secret Values (12.0): never let a secret leak into SavedVariables.
function ns.IsSecret(v)
  if issecretvalue then
    local ok, secret = pcall(issecretvalue, v)
    return ok and secret
  end
  return false
end

-- Returns v only if it is a plain, SavedVariables-safe scalar.
function ns.Clean(v)
  local t = type(v)
  if t ~= "string" and t ~= "number" and t ~= "boolean" then return nil end
  if ns.IsSecret(v) then return nil end
  if t == "number" and v ~= v then return nil end -- NaN
  return v
end

function ns.CleanString(v)
  v = ns.Clean(v)
  if type(v) == "string" and v ~= "" then return v end
  return nil
end

function ns.Trim(s)
  if type(s) ~= "string" then return "" end
  return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

function ns.Slug(s)
  s = tostring(s or ""):lower()
  s = s:gsub("[^%w]+", "-"):gsub("^%-+", ""):gsub("%-+$", "")
  if s == "" then s = "unknown" end
  return s
end

function ns.Now()
  return time()
end

function ns.FormatDuration(seconds)
  seconds = math.floor(tonumber(seconds) or 0)
  if seconds < 0 then seconds = 0 end
  local h = math.floor(seconds / 3600)
  local m = math.floor((seconds % 3600) / 60)
  local s = seconds % 60
  return string.format("%02d:%02d:%02d", h, m, s)
end

function ns.FormatClock(epoch)
  local s = date("%I:%M %p", epoch)
  return (s:gsub("^0", ""))
end

-- A client format string ("%s dies, you gain %d experience.") as an anchored Lua pattern with captures.
function ns.FormatToPattern(fmt)
  local p = fmt:gsub("%%s", "\1"):gsub("%%d", "\2")
  p = p:gsub("[%(%)%.%%%+%-%*%?%[%]%^%$]", "%%%0")
  p = p:gsub("\1", "(.-)"):gsub("\2", "(%%d+)")
  return "^" .. p .. "$"
end

-- pcall wrapper: returns the results on success, nil on failure (and records the error).
function ns.SafeCall(fn, ...)
  if type(fn) ~= "function" then return nil end
  local results = { pcall(fn, ...) }
  if results[1] then
    return select(2, unpack(results))
  end
  ns.Warn(tostring(results[2]))
  return nil
end

-- RegisterEvent throws on events the client does not know. Record and move on.
function ns.SafeRegister(frame, event)
  local ok, err = pcall(frame.RegisterEvent, frame, event)
  if not ok then
    table.insert(ns.failedEvents, event)
    ns.Debug("event not available: " .. event)
  end
  return ok
end

function ns.Count(tbl)
  local n = 0
  if type(tbl) == "table" then
    for _ in pairs(tbl) do n = n + 1 end
  end
  return n
end
