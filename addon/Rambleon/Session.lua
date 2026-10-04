-- Rambleon: the in-memory session and the RambleonDB SavedVariables shape.
-- Rule: every value stored under RambleonDB must be a string, number, boolean or table of those.
-- Rule: never trust that RambleonDB was restored (Forever beta bug). Every login may be a fresh table.
local ADDON, ns = ...

local RESUME_WINDOW = 600      -- seconds: resume a suspended session if it was seen this recently
local KEEP_SESSIONS = 10       -- non-active sessions kept in the SV table (the Mac archive owns history)
local HEARTBEAT = 30           -- seconds

ns.session = nil
ns.questTitles = {}
ns.turnedIn = {}                -- questID -> true once handed in (a quest leaving the log was not abandoned)
ns.currentGroup = {}           -- name -> { since = GetTime() }
ns.lastZoneKey = nil
ns.inInstance = nil             -- nil until the first look; then true or false
ns.instanceName = nil
ns.isDead = false
ns.lastDeathAt = nil
ns.dbRestored = false
ns.dirty = false               -- UI refresh hint
ns.resumed = false
ns.lastXP, ns.lastXPMax = nil, nil
ns.doneObjectives = {}
ns.objectivesSeeded = false

-- Settings -------------------------------------------------------------------
-- RambleonDB.settings. A new setting is one line here; its type is the type of its default.
local DEFAULTS = {
  autoScreenshots = true,      -- pictures at level ups, marks and new zones
  debug = false,               -- debug chatter in chat
  welcomed = false,            -- the first-run welcome has been shown
}

function ns.GetSetting(key)
  local default = DEFAULTS[key]
  local settings = RambleonDB and RambleonDB.settings
  if type(settings) == "table" and type(settings[key]) == type(default) then return settings[key] end
  return default
end

function ns.SetSetting(key, value)
  local default = DEFAULTS[key]
  value = ns.Clean(value)
  if default == nil or type(value) ~= type(default) then return ns.GetSetting(key) end
  if RambleonDB and type(RambleonDB.settings) == "table" then RambleonDB.settings[key] = value end
  if key == "debug" then ns.debugEnabled = value end
  return ns.GetSetting(key)
end

-- Schema migrations: ns.MIGRATIONS[n] turns a version n-1 table into version n. None yet (the schema is 1).
ns.MIGRATIONS = {}

function ns.Migrate(db, from)
  if from > ns.SCHEMA_VERSION then
    ns.Warn("RambleonDB was written by a newer Rambleon (schema " .. from .. "); leaving it as it is")
    return false
  end
  for v = from + 1, ns.SCHEMA_VERSION do
    local step = ns.MIGRATIONS[v]
    if step then
      local ok, err = pcall(step, db)
      if not ok then ns.Warn("migration to schema " .. v .. " failed: " .. tostring(err)) end
    end
  end
  return true
end

function ns.InitDB()
  ns.dbRestored = false
  if type(RambleonDB) == "table" then
    ns.dbRestored = type(RambleonDB.sessions) == "table" and #RambleonDB.sessions > 0
  else
    RambleonDB = {}
  end
  local stored = tonumber(RambleonDB.schemaVersion) or ns.SCHEMA_VERSION
  if ns.Migrate(RambleonDB, stored) then RambleonDB.schemaVersion = ns.SCHEMA_VERSION end
  RambleonDB.addonVersion = ns.VERSION
  if type(RambleonDB.sessions) ~= "table" then RambleonDB.sessions = {} end
  if type(RambleonDB.settings) ~= "table" then RambleonDB.settings = {} end
  for key, default in pairs(DEFAULTS) do
    if type(RambleonDB.settings[key]) ~= type(default) then RambleonDB.settings[key] = default end
  end
  ns.debugEnabled = ns.GetSetting("debug")
end

-- Location ------------------------------------------------------------------

function ns.GetLocation()
  local loc = {}
  loc.zone = ns.CleanString(ns.SafeCall(GetRealZoneText)) or ns.CleanString(ns.SafeCall(GetZoneText))
  loc.subzone = ns.CleanString(ns.SafeCall(GetSubZoneText))
  if loc.subzone == loc.zone then loc.subzone = nil end
  if C_Map and C_Map.GetBestMapForUnit then
    loc.mapID = ns.Clean(ns.SafeCall(C_Map.GetBestMapForUnit, "player"))
  end
  local inInstance = ns.SafeCall(IsInInstance)
  if loc.mapID and not inInstance and C_Map.GetPlayerMapPosition then
    local pos = ns.SafeCall(C_Map.GetPlayerMapPosition, loc.mapID, "player")
    if pos and pos.GetXY then
      local x, y = ns.SafeCall(pos.GetXY, pos)
      x, y = ns.Clean(x), ns.Clean(y)
      if x and y then
        loc.x = math.floor(x * 1000 + 0.5) / 10   -- percent with one decimal
        loc.y = math.floor(y * 1000 + 0.5) / 10
      end
    end
  end
  return loc
end

-- Identity ------------------------------------------------------------------

function ns.CaptureCharacter()
  local c = {}
  c.name = ns.CleanString(ns.SafeCall(UnitName, "player"))
  if UnitFullName then
    local n, r = ns.SafeCall(UnitFullName, "player")
    c.fullName = ns.CleanString(n)
    c.realmFromFullName = ns.CleanString(r)
  end
  c.realm = ns.CleanString(ns.SafeCall(GetRealmName))
  c.normalizedRealm = ns.CleanString(ns.SafeCall(GetNormalizedRealmName))
  -- Forever build 70009 moved the surname into UnitFullName's second return ("Rambleon", "Birdsong") and
  -- dropped it from UnitName; earlier builds returned "Rambleon Birdsong", "ClassicBetaPvE". Keep the raw
  -- fields as reported and derive one stable display name from them (identity itself is the GUID).
  c.surname = ns.Surname(c)
  c.displayName = ns.ComposeDisplayName(c)
  local race, raceFile = ns.SafeCall(UnitRace, "player")
  c.race, c.raceFile = ns.CleanString(race), ns.CleanString(raceFile)
  local class, classFile = ns.SafeCall(UnitClass, "player")
  c.class, c.classFile = ns.CleanString(class), ns.CleanString(classFile)
  c.faction = ns.CleanString(ns.SafeCall(UnitFactionGroup, "player"))
  local sex = ns.Clean(ns.SafeCall(UnitSex, "player"))     -- 2 = male, 3 = female, 1 = unknown
  c.gender = (sex == 2 and "male") or (sex == 3 and "female") or nil
  c.guid = ns.CleanString(ns.SafeCall(UnitGUID, "player"))
  c.startLevel = ns.Clean(ns.SafeCall(UnitLevel, "player"))
  c.endLevel = c.startLevel
  return c
end

function ns.CaptureClient()
  local cl = {}
  local v, b, d, toc = ns.SafeCall(GetBuildInfo)
  cl.version, cl.build, cl.buildDate, cl.tocVersion = ns.Clean(v), ns.Clean(b), ns.Clean(d), ns.Clean(toc)
  cl.projectId = ns.Clean(WOW_PROJECT_ID)
  cl.flavorHint = ns.flavorHint
  cl.addonVersion = ns.VERSION
  cl.locale = ns.Clean(ns.SafeCall(GetLocale))
  if ns.flavorHint == "forever" then
    cl.flavor = "forever"
  elseif cl.tocVersion == 16001 then
    cl.flavor = "forever?"
  else
    cl.flavor = "unknown"
  end
  return cl
end

-- The second return of UnitFullName is a surname when it is not the realm (any spelling) and the name has none.
function ns.Surname(c)
  local r = c.realmFromFullName
  local name = c.fullName or c.name
  if type(r) ~= "string" or r == "" or type(name) ~= "string" or name:find(" ", 1, true) then return nil end
  local realm, normalized = c.realm, c.normalizedRealm
  if r == realm or r == normalized then return nil end
  if type(realm) == "string" and r == (realm:gsub("%s+", "")) then return nil end
  return r
end

function ns.ComposeDisplayName(c)
  local name = c.fullName or c.name
  if type(name) ~= "string" or name == "" then return nil end
  local surname = c.surname or ns.Surname(c)
  if surname and name:sub(-#surname) ~= surname then return name .. " " .. surname end
  return name
end

function ns.DisplayName()
  local c = ns.session and ns.session.character
  return (c and (c.displayName or c.fullName or c.name)) or ns.CleanString(ns.SafeCall(UnitName, "player")) or "Adventurer"
end

-- Session lifecycle ----------------------------------------------------------

local function newSessionId(character)
  local stamp = date("!%Y-%m-%dT%H%M%SZ")
  local base = stamp .. "_" .. ns.Slug(character.displayName or character.fullName or character.name or "unknown")
  local id, n = base, 1
  local taken = true
  while taken do
    taken = false
    for _, s in ipairs(RambleonDB.sessions) do
      if type(s) == "table" and s.id == id then taken = true break end
    end
    if taken then n = n + 1; id = base .. "-" .. n end
  end
  return id
end

-- Identity is the GUID; the name only decides for sessions recorded before the GUID was (the client has
-- changed how it spells the name between builds).
local function sameCharacter(a, b)
  if a.guid and b.guid then return a.guid == b.guid end
  return a.name ~= nil and a.name == b.name
end

local function findResumable(character)
  local now = ns.Now()
  for i = #RambleonDB.sessions, 1, -1 do
    local s = RambleonDB.sessions[i]
    if type(s) == "table" and s.state == "suspended" and type(s.character) == "table"
       and sameCharacter(s.character, character)
       and type(s.lastSeen) == "number" and (now - s.lastSeen) <= RESUME_WINDOW then
      return s
    end
  end
  return nil
end

function ns.PruneSessions()
  local sessions = RambleonDB.sessions
  local nonActive = 0
  for _, s in ipairs(sessions) do
    if type(s) ~= "table" or s.state ~= "active" then nonActive = nonActive + 1 end
  end
  local i = 1
  while nonActive > KEEP_SESSIONS and i <= #sessions do
    if type(sessions[i]) ~= "table" or sessions[i].state ~= "active" then
      table.remove(sessions, i)
      nonActive = nonActive - 1
    else
      i = i + 1
    end
  end
end

function ns.StartSession()
  local character = ns.CaptureCharacter()
  local resumed = findResumable(character)
  ns.playedAnchor = GetTime()
  ns.currentGroup = {}
  ns.resumed = false
  ns.doneObjectives = {}
  ns.objectivesSeeded = false
  if resumed then
    ns.session = resumed
    resumed.state = "active"
    resumed.resumes = (resumed.resumes or 0) + 1
    resumed.kills = resumed.kills or {}
    ns.resumed = true
    ns.AddEvent("RESUMED", {})
    ns.SeedFromSession()
    ns.Debug("resumed session " .. resumed.id)
    return resumed
  end
  local s = {
    id = newSessionId(character),
    schemaVersion = ns.SCHEMA_VERSION,
    state = "active",
    startedAt = ns.Now(),
    startedServerTime = ns.Clean(ns.SafeCall(GetServerTime)),
    lastSeen = ns.Now(),
    playedSeconds = 0,
    character = character,
    client = ns.CaptureClient(),
    counters = ns.NewCounters(),
    zones = {},
    people = {},
    kills = {},                 -- name -> { count, xp, firstAt, lastAt }
    events = {},
    failedEvents = {},
  }
  for _, e in ipairs(ns.failedEvents) do table.insert(s.failedEvents, e) end
  table.insert(RambleonDB.sessions, s)
  ns.session = s
  ns.PruneSessions()
  ns.lastZoneKey = nil
  ns.AddEvent("SESSION_START", {})
  ns.Debug("new session " .. s.id)
  return s
end

-- After a resume, remember where we were and who we were with so nothing is logged twice.
function ns.SeedFromSession()
  local s = ns.session
  if not s then return end
  for i = #s.events, 1, -1 do
    local ev = s.events[i]
    if ev.type == "ZONE_ENTER" and ev.zone then
      ns.lastZoneKey = ev.zone .. "|" .. (ev.subzone or "")
      break
    end
  end
  -- Inside a dungeon when the session was last seen: a /reload in there is not a second arrival.
  ns.inInstance, ns.instanceName = false, nil
  for i = #s.events, 1, -1 do
    local ev = s.events[i]
    if ev.type == "INSTANCE_ENTER" or ev.type == "INSTANCE_EXIT" then
      ns.inInstance = ev.type == "INSTANCE_ENTER"
      ns.instanceName = ns.inInstance and ev.name or nil
      break
    end
  end
  ns.UpdateRoster(true)
end

-- Any recorder call goes through this: after END CHAPTER (without a reload) a new chapter starts.
function ns.EnsureSession()
  if not ns.session or ns.session.state ~= "active" then
    if not ns.loaded then return nil end
    ns.StartSession()
  end
  return ns.session
end

function ns.PlayedSeconds()
  local s = ns.session
  if not s then return 0 end
  local base = s.playedSeconds or 0
  if s.state == "active" and ns.playedAnchor then
    base = base + (GetTime() - ns.playedAnchor)
  end
  return base
end

local function flushPlaytime()
  local s = ns.session
  if not s or s.state ~= "active" or not ns.playedAnchor then return end
  local now = GetTime()
  s.playedSeconds = math.floor(((s.playedSeconds or 0) + (now - ns.playedAnchor)) + 0.5)
  ns.playedAnchor = now
  s.lastSeen = ns.Now()
end

function ns.FlushPeople()
  local s = ns.session
  if not s then return end
  local now = GetTime()
  for name, g in pairs(ns.currentGroup) do
    local p = ns.FindPerson(name)
    if p then
      p.seconds = math.floor((p.seconds or 0) + (now - g.since) + 0.5)
      p.lastSeen = ns.Now()
    end
    g.since = now
  end
end

function ns.Heartbeat()
  if not ns.session or ns.session.state ~= "active" then return end
  flushPlaytime()
  ns.FlushPeople()
  ns.dirty = true
end

function ns.EndSession(reason)
  local s = ns.session
  if not s or s.state ~= "active" then return nil end
  flushPlaytime()
  ns.FlushPeople()
  s.character.endLevel = ns.Clean(ns.SafeCall(UnitLevel, "player")) or s.character.endLevel
  ns.AddEvent("SESSION_END", { reason = reason or "end_chapter" })
  s.state = "ended"
  s.endedAt = ns.Now()
  s.endReason = reason or "end_chapter"
  ns.playedAnchor = nil
  ns.dirty = true
  return s
end

function ns.SuspendSession()
  local s = ns.session
  if not s or s.state ~= "active" then return end
  flushPlaytime()
  ns.FlushPeople()
  s.character.endLevel = ns.Clean(ns.SafeCall(UnitLevel, "player")) or s.character.endLevel
  s.state = "suspended"
  s.lastSeen = ns.Now()
  ns.playedAnchor = nil
end

-- Events ---------------------------------------------------------------------

-- The one way an event is recorded. What the type means (its line in the log, its counter) is in EventTypes.lua.
local unknownTypes = {}

function ns.AddEvent(eventType, fields)
  local s = ns.session
  if not s then return nil end
  local ev = { t = ns.Now(), type = eventType }
  for k, v in pairs(fields or {}) do
    local clean = ns.Clean(v)
    if clean ~= nil then ev[k] = clean end
  end
  if ev.level == nil then ev.level = ns.Clean(ns.SafeCall(UnitLevel, "player")) end
  if ev.zone == nil and eventType ~= "ZONE_ENTER" and eventType ~= "SESSION_START" then
    local loc = ns.GetLocation()
    ev.zone, ev.subzone = loc.zone, loc.subzone
  end
  table.insert(s.events, ev)
  -- The level on every event is the source of truth for endLevel; UnitLevel at logout proved unreliable.
  if type(ev.level) == "number" and ev.level > (tonumber(s.character.endLevel) or 0) then
    s.character.endLevel = ev.level
  end
  local def = ns.EVENT_TYPES[eventType]
  if def and def.counter then
    s.counters[def.counter] = (s.counters[def.counter] or 0) + 1
  elseif not def and not unknownTypes[eventType] then   -- still recorded: a memory is never dropped over a typo
    unknownTypes[eventType] = true
    ns.Warn("event type " .. tostring(eventType) .. " is not in EventTypes.lua")
  end
  s.lastSeen = ev.t
  ns.dirty = true
  ns.Debug(eventType)
  return ev
end

-- Zones ----------------------------------------------------------------------

function ns.RecordZone(loc)
  local s = ns.session
  if not s or not loc.zone then return end
  local key = loc.zone .. "|" .. (loc.subzone or "")
  for _, z in ipairs(s.zones) do
    if (z.zone .. "|" .. (z.subzone or "")) == key then
      z.visits = (z.visits or 1) + 1
      z.lastSeen = ns.Now()
      return z
    end
  end
  local z = { zone = loc.zone, subzone = loc.subzone, mapID = loc.mapID,
              firstSeen = ns.Now(), lastSeen = ns.Now(), visits = 1 }
  table.insert(s.zones, z)
  s.counters.zonesVisited = #s.zones
  return z
end

local function zoneVisited(zone)
  local s = ns.session
  if not s then return false end
  for _, z in ipairs(s.zones) do
    if z.zone == zone then return true end
  end
  return false
end

function ns.NoteZoneChange(force)
  if not ns.EnsureSession() then return end
  local loc = ns.GetLocation()
  if not loc.zone then return end
  local key = loc.zone .. "|" .. (loc.subzone or "")
  if key == ns.lastZoneKey and not force then return end
  -- A picture of the first arrival in a new main zone tonight. Not at login (no previous zone),
  -- not for subzone hops, not after a /reload (SeedFromSession restores lastZoneKey).
  local prevZone = ns.lastZoneKey and ns.lastZoneKey:match("^(.-)|") or nil
  local firstVisit = prevZone ~= nil and prevZone ~= loc.zone and not zoneVisited(loc.zone)
  ns.lastZoneKey = key
  ns.RecordZone(loc)
  ns.AddEvent("ZONE_ENTER", { zone = loc.zone, subzone = loc.subzone, mapID = loc.mapID, x = loc.x, y = loc.y })
  if firstVisit then ns.TakeScreenshot("ZONE_ENTER", { zone = loc.zone, subzone = loc.subzone }, 1.0) end
end

-- People ---------------------------------------------------------------------

function ns.FindPerson(name)
  local s = ns.session
  if not s then return nil end
  for _, p in ipairs(s.people) do
    if p.name == name then return p end
  end
  return nil
end

function ns.UpdateRoster(silent)
  local s = ns.EnsureSession()
  if not s then return end
  local present = {}
  local inGroup = ns.SafeCall(IsInGroup)
  if inGroup then
    local n = ns.SafeCall(GetNumGroupMembers) or 0
    local inRaid = ns.SafeCall(IsInRaid)
    for i = 1, n do
      local unit = (inRaid and "raid" or "party") .. i
      if ns.SafeCall(UnitExists, unit) and not ns.SafeCall(UnitIsUnit, unit, "player") then
        local name = ns.CleanString(ns.SafeCall(UnitName, unit))
        if name and name ~= UNKNOWNOBJECT then
          local class, classFile = ns.SafeCall(UnitClass, unit)
          present[name] = { class = ns.CleanString(class), classFile = ns.CleanString(classFile) }
        end
      end
    end
  end
  local now = GetTime()
  for name, info in pairs(present) do
    if not ns.currentGroup[name] then
      ns.currentGroup[name] = { since = now }
      local p = ns.FindPerson(name)
      if not p then
        p = { name = name, class = info.class, classFile = info.classFile,
              firstSeen = ns.Now(), lastSeen = ns.Now(), seconds = 0, joins = 0 }
        table.insert(s.people, p)
      end
      p.lastSeen = ns.Now()
      if not silent then
        p.joins = (p.joins or 0) + 1
        ns.AddEvent("GROUP_JOIN", { name = name, class = info.class })
      end
    end
  end
  for name, g in pairs(ns.currentGroup) do
    if not present[name] then
      local p = ns.FindPerson(name)
      if p then
        p.seconds = math.floor((p.seconds or 0) + (now - g.since) + 0.5)
        p.lastSeen = ns.Now()
      end
      ns.currentGroup[name] = nil
      ns.AddEvent("GROUP_LEAVE", { name = name })
    end
  end
end

-- Kills and experience --------------------------------------------------------
-- Source: the "X dies, you gain N experience." chat line. Only XP-granting kills are visible this way;
-- Rambleon never touches the combat log.

local xpPatterns
local function buildXpPatterns()
  if xpPatterns then return xpPatterns end
  xpPatterns = {}
  -- Client globals first (localised), English fallbacks after. Nil globals must not stop the loop.
  local formats = {}
  for _, fmt in pairs({ COMBATLOG_XPGAIN_FIRSTPERSON_GROUP, COMBATLOG_XPGAIN_FIRSTPERSON_RAID, COMBATLOG_XPGAIN_FIRSTPERSON }) do
    table.insert(formats, fmt)
  end
  table.insert(formats, "%s dies, you gain %d experience. (+%d group bonus)")
  table.insert(formats, "%s dies, you gain %d experience. (+%d raid bonus)")
  table.insert(formats, "%s dies, you gain %d experience.")
  local seen = {}
  for _, fmt in ipairs(formats) do
    if type(fmt) == "string" and not seen[fmt] then
      seen[fmt] = true
      table.insert(xpPatterns, ns.FormatToPattern(fmt))
    end
  end
  return xpPatterns
end

function ns.RecordKillFromChat(text)
  text = ns.CleanString(text)
  if not text then return end
  local s = ns.EnsureSession()
  if not s then return end
  local name, xp
  for _, pattern in ipairs(buildXpPatterns()) do
    name, xp = text:match(pattern)
    if name then break end
  end
  if not name or name == "" then return end
  xp = tonumber(xp) or 0
  s.kills = s.kills or {}
  local k = s.kills[name]
  if not k then
    k = { count = 0, xp = 0, firstAt = ns.Now(), lastAt = ns.Now() }
    s.kills[name] = k
    ns.AddEvent("FIRST_KILL", { name = name, xp = xp })
  end
  k.count = k.count + 1
  k.xp = k.xp + xp
  k.lastAt = ns.Now()
  s.counters.kills = (s.counters.kills or 0) + 1
  s.lastSeen = ns.Now()
  ns.dirty = true
end

function ns.SeedXP()
  ns.lastXP = ns.Clean(ns.SafeCall(UnitXP, "player"))
  ns.lastXPMax = ns.Clean(ns.SafeCall(UnitXPMax, "player"))
end

function ns.UpdateXP()
  local s = ns.session
  if not s or s.state ~= "active" then return end
  local xp = ns.Clean(ns.SafeCall(UnitXP, "player"))
  local max = ns.Clean(ns.SafeCall(UnitXPMax, "player"))
  if type(xp) ~= "number" then return end
  if type(ns.lastXP) == "number" then
    local delta
    if xp >= ns.lastXP then
      delta = xp - ns.lastXP
    else
      delta = ((ns.lastXPMax or 0) - ns.lastXP) + xp   -- levelled up in between
    end
    if delta > 0 then s.counters.xpGained = (s.counters.xpGained or 0) + delta end
  end
  ns.lastXP, ns.lastXPMax = xp, max
end

-- Quest objectives: "8/8 Timberling slain" finishing is a memory; each kill on the way is not.
function ns.ScanObjectives()
  local s = ns.session
  if not s or s.state ~= "active" then return end
  if not (C_QuestLog and C_QuestLog.GetNumQuestLogEntries and C_QuestLog.GetInfo and C_QuestLog.GetQuestObjectives) then return end
  local n = ns.SafeCall(C_QuestLog.GetNumQuestLogEntries) or 0
  for i = 1, n do
    local info = ns.SafeCall(C_QuestLog.GetInfo, i)
    if type(info) == "table" and not info.isHeader and type(info.questID) == "number" then
      local title = ns.CleanString(info.title)
      if title then ns.questTitles[info.questID] = title end
      local objectives = ns.SafeCall(C_QuestLog.GetQuestObjectives, info.questID)
      if type(objectives) == "table" then
        for idx, obj in ipairs(objectives) do
          if type(obj) == "table" and obj.finished then
            local key = info.questID .. "#" .. idx
            if not ns.doneObjectives[key] then
              ns.doneObjectives[key] = true
              if ns.objectivesSeeded then
                ns.AddEvent("OBJECTIVE_COMPLETE", { questID = info.questID, title = title, text = ns.CleanString(obj.text) })
              end
            end
          end
        end
      end
    end
  end
  ns.objectivesSeeded = true
end

-- Loot worth remembering -----------------------------------------------------
-- Uncommon (green) or better items you receive or equip. Greys and whites are noise.

local MIN_QUALITY = 2
local QUALITY_NAMES = { [0] = "Poor", "Common", "Uncommon", "Rare", "Epic", "Legendary", "Artifact", "Heirloom" }
local LINK_COLORS = { ["1eff00"] = 2, ["0070dd"] = 3, ["a335ee"] = 4, ["ff8000"] = 5, ["e6cc80"] = 6, ["00ccff"] = 7 }

local function itemFromLink(link)
  if type(link) ~= "string" then return nil end
  -- The link itself: |Hitem:<id>:...|h[Name]|h. The colour before it comes in two spellings on the 12.x codebase:
  -- the classic |cff1eff00 and the named |cnIQ2: (IQ = item quality), which is what the Forever client sends.
  local itemID, name = link:match("|Hitem:(%d+)[^|]*|h%[([^%]]*)%]|h")
  if not itemID then return nil end
  itemID = tonumber(itemID)
  local quality
  if C_Item and C_Item.GetItemQualityByID then
    quality = ns.Clean(ns.SafeCall(C_Item.GetItemQualityByID, itemID))
  end
  if type(quality) ~= "number" then
    local named = link:match("|cnIQ(%d+):|Hitem:")
    local hex = link:match("|c%x%x(%x%x%x%x%x%x)|Hitem:")
    quality = tonumber(named) or (hex and LINK_COLORS[hex:lower()]) or 1
  end
  return { itemID = itemID, name = ns.CleanString(name), quality = quality }
end

local lootPatterns
local function buildLootPatterns()
  if lootPatterns then return lootPatterns end
  lootPatterns = {}
  local formats = {}
  for _, fmt in pairs({ LOOT_ITEM_SELF_MULTIPLE, LOOT_ITEM_PUSHED_SELF_MULTIPLE, LOOT_ITEM_CREATED_SELF_MULTIPLE,
                        LOOT_ITEM_SELF, LOOT_ITEM_PUSHED_SELF, LOOT_ITEM_CREATED_SELF }) do
    table.insert(formats, fmt)
  end
  for _, fmt in ipairs({ "You receive loot: %sx%d.", "You receive item: %sx%d.", "You create: %sx%d.",
                         "You receive loot: %s.", "You receive item: %s.", "You create: %s." }) do
    table.insert(formats, fmt)
  end
  -- Patterns with a quantity must be tried first, or "…x2." is swallowed by the singular form.
  local seen, multiples, singles = {}, {}, {}
  for _, fmt in ipairs(formats) do
    if type(fmt) == "string" and not seen[fmt] then
      seen[fmt] = true
      table.insert(fmt:find("%%d") and multiples or singles, ns.FormatToPattern(fmt))
    end
  end
  for _, p in ipairs(multiples) do table.insert(lootPatterns, p) end
  for _, p in ipairs(singles) do table.insert(lootPatterns, p) end
  return lootPatterns
end

-- Loot diagnostics for /ramble debug: how many loot lines arrived, how many we could read, the last one we could not.
ns.lootStats = { lines = 0, parsed = 0, kept = 0, lastUnparsed = nil }

function ns.RecordLootFromChat(text)
  local stats = ns.lootStats
  stats.lines = stats.lines + 1
  text = ns.CleanString(text)
  if not text then stats.lastUnparsed = "(secret or empty)"; return end
  local link, count
  for _, pattern in ipairs(buildLootPatterns()) do
    link, count = text:match(pattern)
    if link then break end
  end
  if not link then
    if not text:find("^You ") then return end   -- someone else's loot: not ours to read
    stats.lastUnparsed = text:sub(1, 160)
    return
  end
  local item = itemFromLink(link)
  if not item then stats.lastUnparsed = text:sub(1, 160); return end
  stats.parsed = stats.parsed + 1
  if item.quality < MIN_QUALITY then return end
  local s = ns.EnsureSession()
  if not s then return end
  ns.AddEvent("LOOT", { itemID = item.itemID, name = item.name, quality = item.quality,
                        qualityName = QUALITY_NAMES[item.quality], count = tonumber(count) or 1 })
  stats.kept = stats.kept + 1
end

ns.equippedSeen = {}
function ns.RecordEquip(slot)
  if type(slot) ~= "number" or not GetInventoryItemLink then return end
  local link = ns.SafeCall(GetInventoryItemLink, "player", slot)
  local item = itemFromLink(link)
  if not item or item.quality < MIN_QUALITY then return end
  local s = ns.EnsureSession()
  if not s then return end
  local key = slot .. ":" .. item.itemID
  if ns.equippedSeen[key] then return end
  ns.equippedSeen[key] = true
  if not ns.equipSeeded then return end   -- the first pass after login just learns what is already worn
  ns.AddEvent("EQUIP", { itemID = item.itemID, name = item.name, quality = item.quality,
                         qualityName = QUALITY_NAMES[item.quality], slot = slot })
end

function ns.SeedEquipment()
  ns.equipSeeded = false
  for slot = 1, 19 do ns.RecordEquip(slot) end
  ns.equipSeeded = true
end

-- Manual moments -------------------------------------------------------------

function ns.AddNote(text)
  text = ns.Trim(text)
  if text == "" then return nil end
  if not ns.EnsureSession() then return nil end
  if #text > ns.NOTE_MAX then text = text:sub(1, ns.NOTE_MAX) end
  return ns.AddEvent("NOTE", { text = text })
end

-- The slash command, the keybinding and the panel button all come through here.
function ns.MarkMoment()
  if not ns.EnsureSession() then return nil end
  local ev = ns.AddEvent("MARK", {})
  ns.TakeScreenshot("MARK", {}, 0.2)
  if ev and ns.UI and ns.UI.MomentRemembered then ns.UI.MomentRemembered() end
  return ev
end

-- Automatic screenshots -------------------------------------------------------
-- The game's own Screenshot() writes WoWScrnShot_*.jpg to <WoW>/Screenshots; the companion pairs the
-- file with the SCREENSHOT event by time. We tag the event with why it was taken so the story page
-- can caption it ("Reached Level 9 in Dolanaar"). The UI is never hidden. Unverified on Forever:
-- everything is guarded, and /ramble debug reports whether it worked.

local AUTO_SHOT_GAP = 3        -- seconds between automatic screenshots (the client dislikes bursts)
local PENDING_TTL = 15         -- seconds a pending reason stays valid for the next SCREENSHOT_SUCCEEDED

ns.pendingShot = nil           -- { reason, at, level, zone, subzone } while a Screenshot() is in flight
ns.restoreUI = nil             -- shows our frames again once the picture is taken
ns.lastAutoShotAt = 0          -- GetTime()
ns.shotStatus = "none"         -- none | ok | failed | unsupported | disabled

function ns.AutoShotsEnabled()
  return ns.GetSetting("autoScreenshots")
end

function ns.SetAutoShots(on)
  return ns.SetSetting("autoScreenshots", on and true or false)
end

function ns.RestoreUIAfterShot()
  local restore = ns.restoreUI
  ns.restoreUI = nil
  if restore then pcall(restore) end
end

-- Returns the pending shot for SCREENSHOT_SUCCEEDED, or nil when the event is a manual screenshot.
function ns.ConsumePendingShot()
  ns.RestoreUIAfterShot()
  local p = ns.pendingShot
  ns.pendingShot = nil
  if p and (ns.Now() - (p.at or 0)) <= PENDING_TTL then return p end
  return nil
end

function ns.TakeScreenshot(reason, fields, delay)
  if not ns.AutoShotsEnabled() then
    ns.shotStatus = "disabled"
    return false
  end
  if type(Screenshot) ~= "function" then
    if ns.shotStatus ~= "unsupported" then ns.Debug("Screenshot() is not available on this client") end
    ns.shotStatus = "unsupported"
    return false
  end
  local now = GetTime and GetTime() or 0
  if now - (ns.lastAutoShotAt or 0) < AUTO_SHOT_GAP then
    ns.Debug("screenshot skipped (" .. tostring(reason) .. ", rate limit)")
    return false
  end
  ns.lastAutoShotAt = now
  local pending = { reason = tostring(reason), at = ns.Now() }
  for k, v in pairs(fields or {}) do
    local clean = ns.Clean(v)
    if clean ~= nil then pending[k] = clean end
  end
  -- Rambleon's own panel must not be in the picture: hide it now, show it again after the client answers.
  ns.RestoreUIAfterShot()
  if ns.UI and ns.UI.HideForScreenshot then ns.restoreUI = ns.UI.HideForScreenshot() end
  local function fire()
    ns.pendingShot = pending
    local ok, err = pcall(Screenshot)
    if not ok then
      ns.pendingShot = nil
      ns.shotStatus = "failed"
      ns.RestoreUIAfterShot()
      ns.Warn("Screenshot() failed (" .. pending.reason .. "): " .. tostring(err))
    else
      ns.Debug("screenshot requested (" .. pending.reason .. ")")
    end
  end
  if C_Timer and C_Timer.After then
    C_Timer.After((delay or 0) + 3, ns.RestoreUIAfterShot)   -- safety net if the client never answers
  end
  if delay and delay > 0 and C_Timer and C_Timer.After then
    C_Timer.After(delay, fire)
  else
    fire()
  end
  return true
end

-- Heartbeat ticker (started once the world is entered)
function ns.StartHeartbeat()
  if ns.heartbeatTicker then return end
  if C_Timer and C_Timer.NewTicker then
    ns.heartbeatTicker = C_Timer.NewTicker(HEARTBEAT, ns.Heartbeat)
  end
end
