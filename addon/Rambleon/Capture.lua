-- Rambleon: what the client says around an event, kept just long enough to make the event a memory.
-- The target you were fighting when you died, the fall that killed you, the flight you took, the place
-- you discovered. Techniques after JourneyTracker (skittlenicks, MIT), checked against the same client.
-- Nothing here is written to RambleonDB directly: every record goes through ns.AddEvent.
local ADDON, ns = ...

local HOSTILE_FRESH = 60        -- seconds: a hostile you targeted this recently can be the killer
local FALL_MIN = 1              -- seconds in the air (two one-second samples) before a death counts as a fall
local FALL_STALE = 1.5          -- seconds: a fall sample older than this says nothing about now
local MIRROR_SLACK = 2          -- seconds left on a breath or fatigue bar that still counts as "ran out"
local MIRROR_STOP_GRACE = 10    -- seconds: the bar stops at death, sometimes before PLAYER_DEAD
local CAUSE_WINDOW = 2          -- seconds between the quest, kill or discovery and the level it caused
local INFO_DEDUPE = 1           -- seconds: the same system line arrives on two events
local SPELL_DEDUPE = 2          -- seconds: the client says a spell was learned on two events
local FLIGHT_TRIES = 10         -- one-second looks for the taxi to lift off after the player chose a node
local BOAT_WINDOW = 480         -- seconds from one dock to the other
local HEARTH_SPELLS = { [8690] = true }   -- Hearthstone

local TAGGED = { rare = true, elite = true, rareelite = true, worldboss = true }

function ns.ResetCapture()
  ns.mobInfo = {}               -- name -> { level, classification, creatureType }; this session only, never saved
  ns.lastHostile = nil
  ns.lastCause = nil
  ns.lastDock = nil
  ns.recentInfo = {}
  ns.recentSpells = {}
  ns.pendingSpell = nil
  ns.pendingLevelUp = nil
  ns.mirror = {}
end
ns.ResetCapture()

-- Zones ----------------------------------------------------------------------

-- The name of the zone map a map belongs to, or nil. Forever hands a building's name ("Lakeshire Inn",
-- "Sentinel Tower") as the zone text while the map is still the zone's; the map wins. Never from a dungeon map.
function ns.ZoneMapName(mapID)
  if type(mapID) ~= "number" or not (C_Map and C_Map.GetMapInfo) then return nil end
  local info, hops = ns.SafeCall(C_Map.GetMapInfo, mapID), 0
  while type(info) == "table" and hops < 6 do
    local mapType = ns.Clean(info.mapType)
    if mapType == 3 then return ns.CleanString(info.name) end
    if mapType == nil or mapType < 3 or mapType == 4 then return nil end   -- world, continent, dungeon: no zone here
    local parent = ns.Clean(info.parentMapID)
    if type(parent) ~= "number" or parent <= 0 then return nil end
    info, hops = ns.SafeCall(C_Map.GetMapInfo, parent), hops + 1
  end
  return nil
end

-- Units ----------------------------------------------------------------------

-- Remember what a hostile unit is, so a chat line or a death can say more than a name.
-- Returns the record it built, or nil. Other players: class only, never a name.
function ns.NoteUnit(unit)
  if not ns.SafeBool(UnitExists, unit) or not ns.SafeBool(UnitCanAttack, "player", unit) then return nil end
  local now = GetTime()
  if ns.SafeBool(UnitIsPlayer, unit) then
    local class = ns.CleanString((ns.SafeCall(UnitClass, unit)))
    ns.lastHostile = { kind = "player", class = class, at = now }
    return ns.lastHostile
  end
  local name = ns.CleanString(ns.SafeCall(UnitName, unit))
  if not name or name == UNKNOWNOBJECT then return nil end
  local level = ns.Clean(ns.SafeCall(UnitLevel, unit))
  if type(level) ~= "number" or level < 1 then level = nil end
  local classification = ns.CleanString(ns.SafeCall(UnitClassification, unit))
  local info = { level = level, classification = classification,
                 creatureType = ns.CleanString(ns.SafeCall(UnitCreatureType, unit)) }
  ns.mobInfo[name] = info
  ns.lastHostile = { kind = "creature", name = name, level = level, classification = classification, at = now }
  return ns.lastHostile
end

-- The tag worth keeping on a creature: rare, elite, rareelite, worldboss. Ordinary is nothing.
function ns.Tag(classification)
  if classification and TAGGED[classification] then return classification end
  return nil
end

-- What a named kill was, if we ever had it targeted.
function ns.MobFields(name)
  local m = ns.mobInfo[name]
  if not m then return {} end
  return { classification = ns.Tag(m.classification), mobLevel = m.level }
end

-- Deaths ---------------------------------------------------------------------

function ns.SampleMovement()
  local now = GetTime()
  ns.lastFallSample = now
  if ns.SafeBool(IsFalling) then
    ns.fallingSince = ns.fallingSince or now
  else
    ns.fallingSince = nil
  end
end

function ns.OnMirrorTimerStart(timer, value, maxValue, scale, paused)
  timer = ns.CleanString(timer)
  if timer ~= "BREATH" and timer ~= "EXHAUSTION" then return end
  ns.mirror[timer] = { value = ns.Clean(value), scale = ns.Clean(scale), paused = ns.Clean(paused), at = GetTime() }
end

function ns.OnMirrorTimerStop(timer)
  timer = ns.CleanString(timer)
  local m = timer and ns.mirror[timer]
  if m then m.stoppedAt = GetTime() end
end

-- Did this bar run out just now? Unknown numbers mean "cannot say", never "yes".
function ns.MirrorExpired(timer, now)
  local m = ns.mirror[timer]
  if not m or type(m.value) ~= "number" or type(m.scale) ~= "number" or m.scale >= 0 then return false end
  if m.stoppedAt and now - m.stoppedAt > MIRROR_STOP_GRACE then return false end
  local elapsed = (m.stoppedAt or now) - m.at
  local left = m.value / 1000 - elapsed * -m.scale
  return left <= MIRROR_SLACK
end

local function killerFromUnit(unit)
  if not ns.SafeBool(UnitExists, unit) or not ns.SafeBool(UnitCanAttack, "player", unit) then return nil end
  if ns.SafeBool(UnitIsDead, unit) then return nil end
  return ns.NoteUnit(unit)
end

-- The fields of a DEATH: what did it. In order of confidence: a fall, a breath or fatigue bar that ran out,
-- the current target, the last hostile targeted within a minute. Nothing certain: nothing said.
function ns.DeathFields()
  local now = GetTime()
  if ns.fallingSince and now - ns.fallingSince >= FALL_MIN and now - (ns.lastFallSample or 0) < FALL_STALE then
    return { killerKind = "fall" }
  end
  if ns.MirrorExpired("BREATH", now) then return { killerKind = "drowning" } end
  if ns.MirrorExpired("EXHAUSTION", now) then return { killerKind = "fatigue" } end
  local k = killerFromUnit("target")
  if not k and ns.lastHostile and now - ns.lastHostile.at <= HOSTILE_FRESH then k = ns.lastHostile end
  if not k then return {} end
  if k.kind == "player" then return { killerKind = "player", killerClass = k.class } end
  local m = ns.mobInfo[k.name] or {}
  return { killerKind = "creature", killer = k.name, killerLevel = k.level or m.level,
           killerClassification = ns.Tag(k.classification or m.classification) }
end

-- Causes ---------------------------------------------------------------------

-- A quest, a kill or a discovery just happened: the next level-up within a moment was its doing.
function ns.NoteCause(kind)
  ns.lastCause = { kind = kind, at = GetTime() }
  local p = ns.pendingLevelUp
  if p and GetTime() - p.at <= CAUSE_WINDOW and p.ev.cause == nil then
    p.ev.cause = kind
    ns.dirty = true
  end
  ns.pendingLevelUp = nil
end

function ns.RecentCause()
  local c = ns.lastCause
  if c and GetTime() - c.at <= CAUSE_WINDOW then return c.kind end
  return nil
end

-- Hearthstone -----------------------------------------------------------------

function ns.OnSpellcastSucceeded(unit, castGUID, spellID)
  if unit ~= "player" then return end
  spellID = ns.Clean(spellID)
  if type(spellID) ~= "number" or not HEARTH_SPELLS[spellID] then return end
  if not ns.EnsureSession() then return end
  ns.lastHearthAt = GetTime()
  ns.AddEvent("HEARTH_USED", { to = ns.CleanString((ns.SafeCall(GetBindLocation))) })
end

-- Flights --------------------------------------------------------------------

local function flightPoll()
  local p = ns.pendingFlight
  if not p then return end
  p.tries = p.tries + 1
  if ns.SafeBool(UnitOnTaxi, "player") then
    ns.pendingFlight = nil
    ns.lastFlightAt = GetTime()
    if ns.EnsureSession() then ns.AddEvent("FLIGHT", { from = p.from, to = p.to }) end
  elseif p.tries < FLIGHT_TRIES and C_Timer and C_Timer.After then
    C_Timer.After(1, flightPoll)
  else
    ns.pendingFlight = nil
  end
end

-- The player chose a destination on the flight master's map. The flight is a fact once the taxi lifts off.
function ns.OnTakeTaxi(index)
  local loc = ns.GetLocation()
  ns.pendingFlight = { to = ns.CleanString(ns.SafeCall(TaxiNodeName, index)), from = loc.subzone or loc.zone, tries = 0 }
  if C_Timer and C_Timer.After then C_Timer.After(1, flightPoll) else flightPoll() end
end

do
  local function hooked(index) pcall(ns.OnTakeTaxi, index) end
  if type(hooksecurefunc) == "function" then
    pcall(hooksecurefunc, "TakeTaxiNode", hooked)
  elseif type(TakeTaxiNode) == "function" then
    local orig = TakeTaxiNode
    TakeTaxiNode = function(...) orig(...); hooked(...) end
  end
end

-- System lines ---------------------------------------------------------------

local infoPatterns
local function buildInfoPatterns()
  if infoPatterns then return infoPatterns end
  infoPatterns = {}
  local function add(kind, ...)
    local seen = {}
    for _, fmt in pairs({ ... }) do
      if type(fmt) == "string" and not seen[fmt] then
        seen[fmt] = true
        table.insert(infoPatterns, { kind = kind, pattern = ns.FormatToPattern(fmt) })
      end
    end
  end
  add("explored_xp", ERR_ZONE_EXPLORED_XP, "Discovered %s: %d experience gained")   -- before the plain form
  add("explored", ERR_ZONE_EXPLORED, "Discovered %s")
  add("taxi", ERR_NEWTAXIPATH, "New flight path discovered!")
  add("spell", ERR_LEARN_SPELL_S, ERR_LEARN_ABILITY_S, "You have learned a new spell: %s.", "You have learned a new ability: %s.")
  return infoPatterns
end

local function seenRecently(text)
  local now = GetTime()
  for k, at in pairs(ns.recentInfo) do
    if now - at > 5 then ns.recentInfo[k] = nil end
  end
  if ns.recentInfo[text] and now - ns.recentInfo[text] < INFO_DEDUPE then return true end
  ns.recentInfo[text] = now
  return false
end

-- "Discovered Lake Al'Ameth", "New flight path discovered!", "You have learned a new spell: X." The client says
-- each on two events (UI_INFO_MESSAGE and CHAT_MSG_SYSTEM); the same line within a second is one line.
function ns.ReadInfoMessage(text)
  text = ns.CleanString(text)
  if not text or seenRecently(text) then return end
  for _, entry in ipairs(buildInfoPatterns()) do
    local a, b = text:match(entry.pattern)
    if a then
      if not ns.EnsureSession() then return end
      if entry.kind == "explored_xp" then
        ns.AddEvent("DISCOVERED", { name = a, xp = tonumber(b) })
        ns.NoteCause("explore")
      elseif entry.kind == "explored" then
        ns.AddEvent("DISCOVERED", { name = a })
        ns.NoteCause("explore")
      elseif entry.kind == "taxi" then
        local loc = ns.GetLocation()
        ns.AddEvent("FLIGHT_PATH_DISCOVERED", { name = loc.subzone or loc.zone })
      elseif entry.kind == "spell" then
        ns.SpellNameFromChat(a)
      end
      return
    end
  end
end

-- Spells ---------------------------------------------------------------------

local function spellName(spellID)
  if C_Spell and C_Spell.GetSpellName then return ns.CleanString(ns.SafeCall(C_Spell.GetSpellName, spellID)) end
  if C_Spell and C_Spell.GetSpellInfo then
    local info = ns.SafeCall(C_Spell.GetSpellInfo, spellID)
    return type(info) == "table" and ns.CleanString(info.name) or nil
  end
  if GetSpellInfo then return ns.CleanString((ns.SafeCall(GetSpellInfo, spellID))) end
  return nil
end

function ns.RecordSpellLearned(spellID)
  spellID = ns.Clean(spellID)
  if type(spellID) ~= "number" or not ns.EnsureSession() then return end
  local now = GetTime()
  if ns.recentSpells[spellID] and now - ns.recentSpells[spellID] < SPELL_DEDUPE then return end
  ns.recentSpells[spellID] = now
  ns.pendingSpell = { ev = ns.AddEvent("SPELL_LEARNED", { spellID = spellID, name = spellName(spellID) }), at = now }
end

-- The chat line names the spell; it completes the event the client announced by id, or stands alone.
function ns.SpellNameFromChat(name)
  local now = GetTime()
  local p = ns.pendingSpell
  if p and now - p.at < SPELL_DEDUPE then
    if p.ev and not p.ev.name then p.ev.name = name; ns.dirty = true end
    return
  end
  if ns.recentSpells[name] and now - ns.recentSpells[name] < SPELL_DEDUPE then return end
  ns.recentSpells[name] = now
  ns.AddEvent("SPELL_LEARNED", { name = name })
end

-- Boats ----------------------------------------------------------------------

-- Nothing in the client says a boat was taken. Two docks of one route within a few minutes, with no hearth
-- and no flight between, is a crossing. Alliance docks seen in game; the Horde zeppelin towers are unverified.
local DOCKS = {
  ["Rut'theran Village"] = true, ["Auberdine"] = true, ["Menethil Harbor"] = true, ["Theramore Isle"] = true,
  ["Booty Bay"] = true, ["Ratchet"] = true, ["Grom'gol Base Camp"] = true, ["Orgrimmar"] = true, ["Undercity"] = true,
}
local ROUTES = {}
for _, pair in ipairs({
  { "Rut'theran Village", "Auberdine" }, { "Auberdine", "Menethil Harbor" }, { "Menethil Harbor", "Theramore Isle" },
  { "Booty Bay", "Ratchet" }, { "Grom'gol Base Camp", "Orgrimmar" }, { "Orgrimmar", "Undercity" },
}) do
  ROUTES[pair[1] .. "|" .. pair[2]] = true
  ROUTES[pair[2] .. "|" .. pair[1]] = true
end

function ns.NoteDock(loc)
  local dock = loc.subzone or loc.zone
  if not dock or not DOCKS[dock] then return end
  local now = GetTime()
  local d = ns.lastDock
  if d and d.name ~= dock and ROUTES[d.name .. "|" .. dock] and now - d.at <= BOAT_WINDOW
     and (ns.lastHearthAt or 0) < d.at and (ns.lastFlightAt or 0) < d.at then
    ns.AddEvent("BOAT_RIDE", { from = d.name, to = dock })
  end
  ns.lastDock = { name = dock, at = now }
end
