-- Minimal WoW API stub for running Rambleon offline under Lua 5.x.
-- Not a faithful client: just enough to load the files, fire events and inspect RambleonDB.
local WoW = {}
_G.WoW = WoW

unpack = unpack or table.unpack
-- Wall-clock time follows the simulated clock, so the fixture's events are spaced like a real evening.
-- The evening is a fixed one (2026-09-20 18:00 UTC): the fixture is the same bytes on every run.
local t0 = 1789927200
time = function() return t0 + math.floor(WoW.clock - 1000) end
date = function(fmt, t) return os.date(fmt, t or time()) end
tinsert = table.insert
UISpecialFrames = {}
StaticPopupDialogs = {}
SlashCmdList = {}
SOUNDKIT = { IG_QUEST_LOG_OPEN = 1 }
CANCEL = "Cancel"
UNKNOWNOBJECT = "Unknown"
WOW_PROJECT_ID = 1
BackdropTemplateMixin = {}
GameFontNormal = {}

WoW.clock = 1000.0
WoW.timers = {}
WoW.frames = {}
WoW.chat = {}
WoW.state = {
  zone = "Teldrassil", subzone = "Shadowglen", mapID = 57, inInstance = false, instanceType = "none",
  level = 10, xp = 900, xpMax = 1000, dead = false, group = {}, questTitles = { [123] = "The Emerald Dreamcatcher", [124] = "Precious Waters" },
}

function GetTime() return WoW.clock end
function GetServerTime() return time() end
function GetBuildInfo() return "1.60.1", "69913", "Sep 17 2026", 16001 end
function GetLocale() return "enUS" end
function GetRealZoneText() return WoW.state.zone end
function GetZoneText() return WoW.state.zone end
function GetSubZoneText() return WoW.state.subzone or "" end
function IsInInstance() return WoW.state.inInstance, WoW.state.instanceType end
function GetInstanceInfo() return WoW.state.instanceName or WoW.state.zone, WoW.state.instanceType end
function UnitName(unit) if unit == "player" then return "Rambleon" end return WoW.state.group[unit] and WoW.state.group[unit].name end
function UnitFullName(unit) if unit == "player" then return "Rambleon Birdsong", "Classic Beta PvE" end end
function GetRealmName() return "Classic Beta PvE" end
function GetNormalizedRealmName() return nil end
function UnitRace() return "Night Elf", "NightElf" end
function UnitClass(unit) if unit == "player" then return "Druid", "DRUID" end local g = WoW.state.group[unit]; if g then return g.class, g.class:upper() end end
function UnitFactionGroup() return "Alliance", "Alliance" end
function UnitSex() return 3 end
function UnitGUID() return "Player-70-000ABCDE" end
function UnitLevel() return WoW.state.level end
function UnitIsDeadOrGhost() return WoW.state.dead end
function UnitExists(unit) return WoW.state.group[unit] ~= nil end
function UnitIsUnit(a, b) return a == b end
function IsInGroup() return next(WoW.state.group) ~= nil end
function IsInRaid() return false end
function GetNumGroupMembers() local n = 0; for _ in pairs(WoW.state.group) do n = n + 1 end; return n > 0 and n + 1 or 0 end
function GetAchievementInfo(id) return id, "Level 10", nil end
function UnitXP() return WoW.state.xp or 0 end
LOOT_ITEM_SELF = "You receive loot: %s."
LOOT_ITEM_SELF_MULTIPLE = "You receive loot: %sx%d."
LOOT_ITEM_PUSHED_SELF = "You receive item: %s."
C_Item = { GetItemQualityByID = function(id) return WoW.state.itemQuality and WoW.state.itemQuality[id] end }
WoW.state.equipped = {}
function GetInventoryItemLink(unit, slot) return WoW.state.equipped[slot] end
function UnitXPMax() return WoW.state.xpMax or 1000 end
COMBATLOG_XPGAIN_FIRSTPERSON = "%s dies, you gain %d experience."
COMBATLOG_XPGAIN_FIRSTPERSON_GROUP = "%s dies, you gain %d experience. (+%d group bonus)"
WoW.state.questLog = {}   -- list of { questID=, title=, objectives = { {text=, finished=} } }
function PlaySound() end
function StaticPopup_Show(name) WoW.lastPopup = name; return {} end
function ReloadUI() WoW.reloadCalled = true end
function issecretvalue() return false end
WoW.screenshots = 0
WoW.failNextScreenshot = false
-- The client writes the file, then fires SCREENSHOT_SUCCEEDED (or _FAILED) a moment later.
function Screenshot()
  WoW.screenshots = WoW.screenshots + 1
  local fail = WoW.failNextScreenshot
  WoW.failNextScreenshot = false
  table.insert(WoW.timers, { at = WoW.clock + 0.1, fn = function()
    WoW.Fire(fail and "SCREENSHOT_FAILED" or "SCREENSHOT_SUCCEEDED")
  end })
end

C_AddOns = { GetAddOnMetadata = function(_, key) if key == "Version" then return "0.1.0-test" end end }
C_Map = {
  GetBestMapForUnit = function() return WoW.state.mapID end,
  GetPlayerMapPosition = function() return { GetXY = function() return 0.4567, 0.7891 end } end,
}
C_QuestLog = {
  GetTitleForQuestID = function(id) return WoW.state.questTitles[id] end,
  GetNumQuestLogEntries = function() return #WoW.state.questLog end,
  GetInfo = function(i) local q = WoW.state.questLog[i]; return q and { questID = q.questID, title = q.title, isHeader = false } end,
  GetQuestObjectives = function(id) for _, q in ipairs(WoW.state.questLog) do if q.questID == id then return q.objectives end end end,
}
C_UI = { Reload = function() WoW.reloadCalled = true end }
C_Timer = {
  After = function(delay, fn) table.insert(WoW.timers, { at = WoW.clock + delay, fn = fn }) end,
  NewTicker = function(period, fn)
    local t = { period = period, fn = fn, cancelled = false }
    t.at = WoW.clock + period
    t.Cancel = function(self) self.cancelled = true end
    table.insert(WoW.timers, t)
    return t
  end,
}

DEFAULT_CHAT_FRAME = { AddMessage = function(_, msg) table.insert(WoW.chat, msg); if WoW.verbose then print(msg) end end }

-- Generic UI object: any unknown method is a no-op returning nothing.
local function newObject(kind)
  local o = { __kind = kind, __scripts = {}, __events = {}, __shown = false, __text = "" }
  setmetatable(o, { __index = function(t, k)
    return function() end
  end })
  o.RegisterEvent = function(self, event)
    if event == "BOGUS_EVENT" then error("Attempt to register unknown event " .. event) end
    self.__events[event] = true
  end
  o.UnregisterEvent = function(self, event) self.__events[event] = nil end
  o.SetScript = function(self, name, fn) self.__scripts[name] = fn end
  o.GetScript = function(self, name) return self.__scripts[name] end
  o.Show = function(self) self.__shown = true; if self.__scripts.OnShow then self.__scripts.OnShow(self) end end
  o.Hide = function(self) self.__shown = false end
  o.IsShown = function(self) return self.__shown end
  o.SetText = function(self, t) self.__text = t end
  o.GetText = function(self) return self.__text end
  o.CreateFontString = function() return newObject("FontString") end
  o.CreateTexture = function() return newObject("Texture") end
  o.SetAtlas = function() error("atlas missing in stub") end
  o.SetFont = function() return true end
  o.GetParent = function(self) return self.__parent end
  return o
end

function CreateFrame(kind, name, parent, template)
  local f = newObject(kind)
  f.__name = name
  f.__parent = parent
  if template and template:find("Backdrop") then f.SetBackdrop = function() end end
  if name then _G[name] = f end
  table.insert(WoW.frames, f)
  return f
end
UIParent = CreateFrame("Frame", "UIParent")

function WoW.Fire(event, ...)
  for _, f in ipairs(WoW.frames) do
    if f.__events[event] and f.__scripts.OnEvent then
      f.__scripts.OnEvent(f, event, ...)
    end
  end
end

function WoW.Advance(seconds)
  local target = WoW.clock + seconds
  while true do
    local nextTimer, idx
    for i, t in ipairs(WoW.timers) do
      if not t.cancelled and t.at <= target and (not nextTimer or t.at < nextTimer.at) then nextTimer, idx = t, i end
    end
    if not nextTimer then break end
    WoW.clock = nextTimer.at
    if nextTimer.period then
      nextTimer.at = nextTimer.at + nextTimer.period
      nextTimer.fn(nextTimer)
    else
      table.remove(WoW.timers, idx)
      nextTimer.fn()
    end
  end
  WoW.clock = target
end

-- Blizzard-style SavedVariables serializer (CRLF, no indentation, trailing commas).
local function quote(s)
  s = s:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", "\\n"):gsub("\r", "\\r")
  return '"' .. s .. '"'
end
local function serialize(v, out)
  local t = type(v)
  if t == "table" then
    out[#out + 1] = "{"
    local n = #v
    for i = 1, n do
      serialize(v[i], out)
      out[#out] = out[#out] .. ","
    end
    local keys = {}
    for k in pairs(v) do
      if not (type(k) == "number" and k >= 1 and k <= n and math.floor(k) == k) then keys[#keys + 1] = k end
    end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    for _, k in ipairs(keys) do
      local keyText = type(k) == "string" and ('["' .. k .. '"]') or ("[" .. tostring(k) .. "]")
      local inner = {}
      serialize(v[k], inner)
      inner[1] = keyText .. " = " .. inner[1]
      inner[#inner] = inner[#inner] .. ","
      for _, line in ipairs(inner) do out[#out + 1] = line end
    end
    out[#out + 1] = "}"
  elseif t == "string" then
    out[#out + 1] = quote(v)
  elseif t == "number" then
    if math.type(v) == "integer" or v == math.floor(v) then out[#out + 1] = string.format("%d", v)
    else out[#out + 1] = string.format("%.16g", v) end
  elseif t == "boolean" then
    out[#out + 1] = tostring(v)
  elseif t == "nil" then
    out[#out + 1] = "nil"
  else
    error("unserializable type " .. t)
  end
end

function WoW.SerializeSavedVariables(globals)
  local out = { "" }
  for _, name in ipairs(globals) do
    local lines = {}
    serialize(_G[name], lines)
    lines[1] = name .. " = " .. lines[1]
    for _, line in ipairs(lines) do out[#out + 1] = line end
  end
  return table.concat(out, "\r\n") .. "\r\n"
end

return WoW
