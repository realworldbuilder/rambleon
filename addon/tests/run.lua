-- Offline smoke test: load Rambleon under the stub, play a scripted session, check the DB is SV-safe,
-- and write a Blizzard-format fixture for the companion's parser tests.
local here = arg[0]:match("^(.*)/[^/]*$") or "."
local addonDir = here .. "/../Rambleon"
local WoW = dofile(here .. "/wowstub.lua")

local ns = {}
local files = { "Forever.lua", "Util.lua", "EventTypes.lua", "Core.lua", "Session.lua", "Journal.lua", "Events.lua", "UI.lua", "Commands.lua" }
for _, f in ipairs(files) do
  local chunk, err = loadfile(addonDir .. "/" .. f)
  assert(chunk, err)
  chunk("Rambleon", ns)
end

local function assertEq(a, b, msg) if a ~= b then error((msg or "") .. ": expected " .. tostring(b) .. " got " .. tostring(a), 2) end end

-- Boot
WoW.Fire("ADDON_LOADED", "Rambleon")
WoW.Fire("PLAYER_LOGIN")
WoW.Fire("PLAYER_ENTERING_WORLD", true, false)
WoW.Advance(2)                                   -- zone debounce fires
assert(ns.session, "session should exist")
assertEq(ns.session.state, "active", "state")
assertEq(ns.session.character.fullName, "Rambleon Birdsong", "fullName")
assertEq(ns.session.character.displayName, "Rambleon Birdsong", "displayName (old build shape)")
assertEq(ns.session.character.surname, nil, "no surname when the name already has one")
assert(ns.session.id:find("_rambleon%-birdsong"), "session id uses the display name")

-- Forever build 70009 shape: UnitName "Rambleon", UnitFullName "Rambleon", "Birdsong". Same display name.
do
  local oldName, oldFull = UnitName, UnitFullName
  UnitName = function(unit) if unit == "player" then return "Rambleon" end return oldName(unit) end
  UnitFullName = function(unit) if unit == "player" then return "Rambleon", "Birdsong" end end
  local c = ns.CaptureCharacter()
  assertEq(c.name, "Rambleon", "raw name kept as reported")
  assertEq(c.realmFromFullName, "Birdsong", "raw second return kept as reported")
  assertEq(c.surname, "Birdsong", "surname (new build shape)")
  assertEq(c.displayName, "Rambleon Birdsong", "displayName (new build shape)")
  -- Mainline shape: the realm in the second slot is never a surname, in any spelling.
  UnitFullName = function(unit) if unit == "player" then return "Rambleon", "ClassicBetaPvE" end end
  c = ns.CaptureCharacter()
  assertEq(c.surname, nil, "realm is not a surname")
  assertEq(c.displayName, "Rambleon", "displayName (mainline shape)")
  UnitName, UnitFullName = oldName, oldFull
end
assertEq(ns.session.client.flavor, "forever", "flavor")
assertEq(ns.session.events[1].type, "SESSION_START", "first event")
assertEq(ns.session.events[2].type, "ZONE_ENTER", "second event")
assertEq(ns.session.events[2].subzone, "Shadowglen", "subzone")

-- Zone spam: same place twice must not add events
WoW.Fire("ZONE_CHANGED"); WoW.Fire("ZONE_CHANGED_INDOORS"); WoW.Advance(2)
assertEq(#ns.session.events, 2, "no duplicate zone event")

-- Travel
WoW.state.subzone = "Dolanaar"; WoW.Fire("ZONE_CHANGED_NEW_AREA"); WoW.Advance(2)
assertEq(ns.session.events[#ns.session.events].subzone, "Dolanaar", "moved to Dolanaar")
assertEq(#ns.session.zones, 2, "two zones")
assertEq(WoW.screenshots, 0, "no screenshot for a subzone hop")

-- First arrival in a new main zone takes a picture; going back to a known zone does not
local function lastOfType(t)
  for i = #ns.session.events, 1, -1 do if ns.session.events[i].type == t then return ns.session.events[i] end end
end
WoW.state.zone = "Darkshore"; WoW.state.subzone = "Auberdine"; WoW.Fire("ZONE_CHANGED_NEW_AREA"); WoW.Advance(3)
assertEq(WoW.screenshots, 1, "screenshot on entering Darkshore")
assertEq(lastOfType("SCREENSHOT").reason, "ZONE_ENTER", "zone screenshot reason")
assertEq(lastOfType("SCREENSHOT").zone, "Darkshore", "zone screenshot zone")
assertEq(lastOfType("SCREENSHOT").auto, true, "zone screenshot is automatic")
assertEq(ns.session.counters.screenshots, 1, "screenshot counter")
WoW.state.zone = "Teldrassil"; WoW.state.subzone = "Dolanaar"; WoW.Fire("ZONE_CHANGED_NEW_AREA"); WoW.Advance(3)
assertEq(WoW.screenshots, 1, "no screenshot when returning to a zone seen tonight")
assertEq(#ns.session.zones, 3, "three zones")

-- Quests
WoW.Fire("QUEST_ACCEPTED", 123)
WoW.Fire("QUEST_ACCEPTED", 5, 124)              -- classic-style args
WoW.Fire("QUEST_TURNED_IN", 123, 450, 0)
assertEq(ns.session.counters.questsAccepted, 2, "accepted")
assertEq(ns.session.counters.questsCompleted, 1, "completed")
assertEq(ns.session.events[#ns.session.events].title, "The Emerald Dreamcatcher", "title")

-- The innkeeper makes Dolanaar home
WoW.state.bind = "Dolanaar"; WoW.Fire("HEARTHSTONE_BOUND")
assertEq(lastOfType("HEARTH_BOUND").name, "Dolanaar", "hearth bound")

-- Level
WoW.state.level = 11; WoW.Fire("PLAYER_LEVEL_UP", 11)
assertEq(ns.session.character.endLevel, 11, "endLevel")
assertEq(WoW.screenshots, 1, "level-up screenshot waits for the glow")
WoW.Advance(2)
assertEq(WoW.screenshots, 2, "screenshot on level up")
assertEq(lastOfType("SCREENSHOT").reason, "LEVEL_UP", "level screenshot reason")
assertEq(lastOfType("SCREENSHOT").level, 11, "level screenshot level")
assertEq(ns.shotStatus, "ok", "shot status ok")

-- Death and revival
WoW.state.dead = true; WoW.Fire("PLAYER_DEAD")
WoW.Advance(3); WoW.Fire("PLAYER_DEAD")          -- build 70009 repeats the event a few seconds later
assertEq(ns.session.counters.deaths, 1, "a repeated PLAYER_DEAD is the same death")
WoW.state.dead = false; WoW.Fire("PLAYER_UNGHOST")
assertEq(ns.session.counters.deaths, 1, "deaths")
assertEq(ns.session.events[#ns.session.events].type, "REVIVED", "revived")

-- People
WoW.state.group.party1 = { name = "Moonhoof", class = "Druid" }
WoW.Fire("GROUP_ROSTER_UPDATE")
WoW.Advance(90)                                  -- heartbeats tick
WoW.Fire("GROUP_ROSTER_UPDATE")                  -- no change → no event
WoW.state.group.party1 = nil
WoW.Fire("GROUP_ROSTER_UPDATE")
assertEq(#ns.session.people, 1, "one person")
assert(ns.session.people[1].seconds >= 89, "grouped seconds ~90, got " .. tostring(ns.session.people[1].seconds))
local joins, leaves = 0, 0
for _, ev in ipairs(ns.session.events) do
  if ev.type == "GROUP_JOIN" then joins = joins + 1 elseif ev.type == "GROUP_LEAVE" then leaves = leaves + 1 end
end
assertEq(joins, 1, "joins"); assertEq(leaves, 1, "leaves")

-- Manual moments via slash commands
ns.HandleSlash("note this cave is extremely cursed")
ns.HandleSlash("mark"); WoW.Advance(1)
assertEq(WoW.screenshots, 3, "screenshot on mark")
assertEq(lastOfType("SCREENSHOT").reason, "MARK", "mark screenshot reason")
ns.HandleSlash("mark"); WoW.Advance(1)              -- a second mark right away: remembered, not photographed
assertEq(WoW.screenshots, 3, "rate limit between automatic screenshots")
ns.HandleSlash("status")
ns.HandleSlash("")                               -- toggles panel (builds UI)
assert(RambleonPanel:IsShown(), "panel shown")
WoW.Advance(3)                                   -- clear the screenshot rate limit
ns.HandleSlash("mark")                           -- MARK MOMENT with the panel open
assert(not RambleonPanel:IsShown(), "panel hidden for the picture")
WoW.Advance(1)
assert(RambleonPanel:IsShown(), "panel back after the picture")
assertEq(lastOfType("SCREENSHOT").reason, "MARK", "panel mark still photographed")
ns.UI.Refresh()
ns.HandleSlash("debug")
ns.HandleSlash("chapters")                       -- builds the chapters frame with no data
assert(RambleonChaptersFrame:IsShown(), "chapters frame shown")
_G.RambleonChapters = { { id = "x", slug = "rambleon-birdsong", date = "Today", duration = "1m", title = "Chapter 1 — Test",
  recap = "1m in Azeroth.", journal = "It was fine.", log = "# log", number = 1, startedAt = 1 } }
ns.UI.ShowChapter(1)
assert(RambleonChaptersText:GetText():find("It was fine"), "chapter text shown")
ns.HandleSlash("chapters")
assertEq(ns.session.counters.notes, 1, "notes")
assertEq(ns.session.counters.marks, 3, "marks")

-- Kills via the XP chat line (no combat log)
WoW.Fire("CHAT_MSG_COMBAT_XP_GAIN", "Timberling dies, you gain 45 experience.")
WoW.Fire("CHAT_MSG_COMBAT_XP_GAIN", "Timberling dies, you gain 45 experience. (+9 group bonus)")
WoW.Fire("CHAT_MSG_COMBAT_XP_GAIN", "Grell dies, you gain 50 experience.")
WoW.Fire("CHAT_MSG_COMBAT_XP_GAIN", "You gain 200 experience.")   -- not a kill
assertEq(ns.session.counters.kills, 3, "kills")
assertEq(ns.session.kills["Timberling"].count, 2, "timberling count")
assertEq(ns.session.kills["Timberling"].xp, 90, "timberling xp")
local firstKills = 0
for _, ev in ipairs(ns.session.events) do if ev.type == "FIRST_KILL" then firstKills = firstKills + 1 end end
assertEq(firstKills, 2, "first kills")

-- XP accounting across a level-up
WoW.state.xp, WoW.state.xpMax = 950, 1000; WoW.Fire("PLAYER_XP_UPDATE", "player")
-- A quest leaving the log: abandoned, unless it was handed in or was never a quest we knew
WoW.state.questTitles[125] = "A Troubling Breeze"
WoW.Fire("QUEST_ACCEPTED", 125); WoW.Fire("QUEST_REMOVED", 125)
WoW.Fire("QUEST_REMOVED", 123); WoW.Fire("QUEST_REMOVED", 999)
WoW.Advance(3)                                   -- clear the screenshot rate limit
assertEq(ns.session.counters.questsAbandoned, 1, "one quest abandoned")
assertEq(lastOfType("QUEST_ABANDONED").title, "A Troubling Breeze", "abandoned quest title")
ns.HandleSlash("shots off")
assertEq(RambleonDB.settings.autoScreenshots, false, "auto shots persisted off")
WoW.state.level = 12; WoW.state.xp, WoW.state.xpMax = 100, 1200; WoW.Fire("PLAYER_LEVEL_UP", 12)
assertEq(ns.session.counters.xpGained, 50 + 50 + 100, "xp gained")
WoW.Advance(2)
assertEq(WoW.screenshots, 4, "no screenshot while shots are off")
ns.HandleSlash("shots on")
assertEq(RambleonDB.settings.autoScreenshots, true, "auto shots persisted on")

-- Quest objectives: first scan seeds silently, later completions are events
WoW.state.questLog = { { questID = 124, title = "Precious Waters", objectives = { { text = "0/8 Timberling slain", finished = false } } } }
WoW.Fire("UNIT_QUEST_LOG_CHANGED", "player"); WoW.Advance(2)
WoW.state.questLog[1].objectives[1] = { text = "8/8 Timberling slain", finished = true }
WoW.Fire("UNIT_QUEST_LOG_CHANGED", "player"); WoW.Advance(2)
WoW.Fire("QUEST_LOG_UPDATE"); WoW.Advance(2)
assertEq(ns.session.counters.objectivesCompleted, 1, "objective completed once")
assertEq(ns.session.events[#ns.session.events].type, "OBJECTIVE_COMPLETE", "objective event")

-- Loot: greens and better only, quest rewards included, equips once per item
local green = "|cff1eff00|Hitem:2044::::::::10:::::|h[Sturdy Bow]|h|r"
local grey = "|cff9d9d9d|Hitem:3771::::::::10:::::|h[Wild Hog Shank]|h|r"
local blue = "|cff0070dd|Hitem:2140::::::::10:::::|h[Arcane Staff]|h|r"
WoW.Fire("CHAT_MSG_LOOT", "You receive loot: " .. grey .. ".")
WoW.Fire("CHAT_MSG_LOOT", "You receive loot: " .. green .. ".")
WoW.Fire("CHAT_MSG_LOOT", "You receive item: " .. blue .. "x2.")
WoW.Fire("CHAT_MSG_LOOT", "Moonhoof receives loot: " .. green .. ".")
assertEq(ns.session.counters.loot, 2, "loot count")
assertEq(ns.session.events[#ns.session.events].name, "Arcane Staff", "loot name")
assertEq(ns.session.events[#ns.session.events].quality, 3, "loot quality from link colour")
assertEq(ns.session.events[#ns.session.events].count, 2, "loot count from x2")
local named = "|cnIQ2:|Hitem:2044::::::::10:::::|h[Sturdy Bow]|h|r"   -- the 12.x named-colour link the Forever client sends
WoW.Fire("CHAT_MSG_LOOT", "You receive loot: " .. named .. ".")
assertEq(ns.session.counters.loot, 3, "named-colour link is read")
assertEq(ns.session.events[#ns.session.events].quality, 2, "quality from |cnIQ2:")
assertEq(ns.lootStats.lines, 5, "loot lines counted"); assertEq(ns.lootStats.parsed, 4, "loot lines read")
assertEq(ns.lootStats.lastUnparsed, nil, "nothing unread")
WoW.Fire("CHAT_MSG_LOOT", "You receive loot: something without a link.")
assertEq(ns.lootStats.lastUnparsed, "You receive loot: something without a link.", "unread line kept for /ramble debug")
WoW.state.equipped[16] = blue
WoW.Fire("PLAYER_EQUIPMENT_CHANGED", 16, true)
WoW.Fire("PLAYER_EQUIPMENT_CHANGED", 16, true)
local equips = 0
for _, ev in ipairs(ns.session.events) do if ev.type == "EQUIP" then equips = equips + 1 end end
assertEq(equips, 1, "one equip event")

-- Screenshot + achievement + instance
WoW.Fire("SCREENSHOT_SUCCEEDED")                 -- the player pressed the screenshot key
assertEq(lastOfType("SCREENSHOT").reason, "MANUAL", "manual screenshot reason")
assertEq(lastOfType("SCREENSHOT").auto, nil, "manual screenshot is not automatic")
WoW.Advance(3)
WoW.failNextScreenshot = true
ns.HandleSlash("mark"); WoW.Advance(1)
assertEq(WoW.screenshots, 5, "screenshot attempted")
assertEq(lastOfType("SCREENSHOT").reason, "MANUAL", "a failed screenshot records no event")
assertEq(ns.shotStatus, "failed", "shot status failed")
assertEq(ns.pendingShot, nil, "pending shot cleared after failure")
WoW.Fire("ACHIEVEMENT_EARNED", 6)
assertEq(lastOfType("ACHIEVEMENT").name, "Level 10", "achievement name")
assertEq(ns.session.counters.achievements, 1, "achievement counter")
WoW.state.inInstance = true; WoW.state.instanceType = "party"; WoW.state.instanceName = "Ragefire Chasm"
WoW.Fire("UPDATE_INSTANCE_INFO")
assertEq(lastOfType("INSTANCE_ENTER").name, "Ragefire Chasm", "instance entered")
WoW.Fire("ENCOUNTER_END", 1444, "Jergosh the Invoker", 1, 5, 0)            -- a wipe is not a kill
WoW.Fire("ENCOUNTER_END", 1443, "Taragaman the Hungerer", 1, 5, 1)
assertEq(lastOfType("BOSS_KILL").name, "Taragaman the Hungerer", "boss kill")
WoW.state.inInstance = false; WoW.state.instanceType = "none"
WoW.Fire("UPDATE_INSTANCE_INFO")
assertEq(lastOfType("INSTANCE_EXIT").name, "Ragefire Chasm", "the exit remembers which instance")

-- End chapter through the UI path
WoW.Advance(280)
ns.UI.PromptEndChapter()
assertEq(WoW.lastPopup, "RAMBLEON_END", "end popup")
StaticPopupDialogs.RAMBLEON_END.OnAccept()
assertEq(ns.session.state, "ended", "ended")
assertEq(ns.session.endReason, "save", "end reason")
assert(WoW.reloadCalled, "reload attempted")
assert(ns.session.playedSeconds >= 370, "played seconds")
local ended = ns.session

-- A /reload with a restored DB resumes the session without duplicating the roster or zone
do
  local saved = ns.session
  ns.session = nil
  ns.enteredWorld = false
  ns.lastZoneKey = nil
  ns.currentGroup = {}
  saved.state = "suspended"; saved.lastSeen = ns.Now()
  WoW.state.group.party1 = { name = "Moonhoof", class = "Druid" }
  WoW.state.subzone = "Dolanaar"
  local before = #saved.events
  WoW.Fire("PLAYER_ENTERING_WORLD", false, true); WoW.Advance(2)
  assert(ns.session == saved, "resumed the suspended session")
  assertEq(ns.session.events[before + 1].type, "RESUMED", "resumed event")
  assertEq(#ns.session.events, before + 1, "no duplicate join/zone after resume")
  WoW.state.group.party1 = nil
  WoW.Fire("GROUP_ROSTER_UPDATE")
  assertEq(ns.session.events[#ns.session.events].type, "GROUP_LEAVE", "leave still detected after resume")
  ns.UI.EndChapterAndReload()
end

-- Marking after an ended chapter starts a fresh chapter automatically
ns.HandleSlash("mark")
assert(ns.session ~= ended, "new session after end")
assertEq(#RambleonDB.sessions, 2, "two sessions in DB")
assert(RambleonDB.sessions[1].id ~= RambleonDB.sessions[2].id, "session ids must differ")

-- Logout suspends
WoW.Fire("PLAYER_LOGOUT")
assertEq(ns.session.state, "suspended", "suspended")

-- SavedVariables safety: only string/number/boolean/table, no NaN
local function check(v, path)
  local t = type(v)
  if t == "table" then
    for k, x in pairs(v) do
      assert(type(k) == "string" or type(k) == "number", "bad key at " .. path)
      check(x, path .. "." .. tostring(k))
    end
  elseif t == "number" then
    assert(v == v, "NaN at " .. path)
  else
    assert(t == "string" or t == "boolean", "bad type " .. t .. " at " .. path)
  end
end
check(RambleonDB, "RambleonDB")
assertEq(#ns.failedEvents, 0, "no failed registrations in stub")

-- One definition per event type: everything recorded is in EventTypes.lua, everything there was recorded here
-- (a new type cannot ship without a line in this script), and no AddEvent call names a type it does not hold.
do
  local emitted = {}
  for _, s in ipairs(RambleonDB.sessions) do
    for _, ev in ipairs(s.events) do
      emitted[ev.type] = true
      assert(ns.EVENT_TYPES[ev.type], "event type missing from EventTypes.lua: " .. tostring(ev.type))
      assert(ns.DescribeEvent(ev) ~= ev.type, "no description for " .. ev.type)
    end
  end
  for eventType in pairs(ns.EVENT_TYPES) do
    assert(emitted[eventType], "EventTypes.lua has " .. eventType .. " but the simulated session never records one")
  end
  for _, f in ipairs(files) do
    local fh = assert(io.open(addonDir .. "/" .. f)); local source = fh:read("a"); fh:close()
    for eventType in source:gmatch('AddEvent%("([A-Z_]+)"') do
      assert(ns.EVENT_TYPES[eventType], f .. " records " .. eventType .. ", which is not in EventTypes.lua")
    end
  end
  assertEq(ns.Count(ns.NewCounters()), 14, "counter keys")
  for key in pairs(ns.NewCounters()) do assert(ended.counters[key] ~= nil, "session lacks counter " .. key) end
end

-- Write the fixture. The companion's tests count on this evening (two sessions, six minutes):
-- anything that needs more time, marks or sessions belongs below, after the fixture.
local fixtureDir = here .. "/../../companion/tests/fixtures"
local text = WoW.SerializeSavedVariables({ "RambleonDB" })
local fh = assert(io.open(fixtureDir .. "/Rambleon_simulated.lua", "wb"))
fh:write(text); fh:close()
local summary = string.format("%d sessions, %d events in session 1, fixture written (%d bytes)",
  #RambleonDB.sessions, #ended.events, #text)

-- After the fixture ---------------------------------------------------------------------------------

local function countOfType(t)
  local n = 0
  for _, ev in ipairs(ns.session.events) do if ev.type == t then n = n + 1 end end
  return n
end

-- Log out and straight back in. `change` may alter the suspended session first.
local function relog(change)
  local saved = ns.session
  ns.SuspendSession()
  if change then change(saved) end
  ns.session = nil
  ns.enteredWorld = false
  WoW.Fire("PLAYER_ENTERING_WORLD", true, false); WoW.Advance(2)
  return saved
end

-- Resuming goes by GUID; the name decides only when a session has none
ns.session = nil; ns.enteredWorld = false
WoW.Fire("PLAYER_ENTERING_WORLD", true, false); WoW.Advance(2)
assertEq(ns.session.state, "active", "back in the world")
local before = relog(function(s) s.character.name = "Rambleon Birdsong" end)   -- the older build's spelling
assert(ns.session == before, "same GUID resumes whatever the name looks like")
before = relog(function(s) s.character.guid = "Player-70-SOMEONE" end)
assert(ns.session ~= before, "another GUID with the same name is another character")
before = relog(function(s) s.character.guid = nil end)
assert(ns.session == before, "a session without a GUID resumes by name")
before = relog(function(s) s.lastSeen = ns.Now() - 601 end)
assert(ns.session ~= before, "no resume after the ten-minute window")

-- Only the last ten finished sessions stay in SavedVariables (the Mac owns history)
for i = 1, 12 do table.insert(RambleonDB.sessions, 1, { id = "old-" .. i, state = "ended" }) end
ns.PruneSessions()
local kept, hasActive = 0, false
for _, s in ipairs(RambleonDB.sessions) do
  if s.state == "active" then hasActive = (s == ns.session) else kept = kept + 1 end
end
assertEq(kept, 10, "ten finished sessions kept"); assert(hasActive, "the active session survives pruning")

-- Settings: defaults fill what is missing, what the player chose stays, debug survives a reload
RambleonDB.settings = { autoScreenshots = false, somethingOld = "kept" }
ns.InitDB()
assertEq(RambleonDB.settings.autoScreenshots, false, "a stored setting is kept")
assertEq(RambleonDB.settings.debug, false, "a missing setting gets its default")
assertEq(RambleonDB.settings.somethingOld, "kept", "unknown keys are left alone")
assertEq(ns.SetSetting("autoScreenshots", "yes"), false, "a value of the wrong type is refused")
assertEq(ns.SetSetting("nonsense", true), nil, "an unknown setting is refused")
ns.HandleSlash("debug on"); ns.InitDB()
assertEq(ns.debugEnabled, true, "debug survives a reload")
ns.HandleSlash("debug off"); ns.SetAutoShots(true)
assertEq(ns.debugEnabled, false, "debug off")

-- Migrations run once, in order, and never on data from a newer Rambleon
do
  local ran = 0
  ns.MIGRATIONS[2] = function(db) ran = ran + 1; db.migrated = true end
  ns.SCHEMA_VERSION = 2
  ns.InitDB()
  assertEq(ran, 1, "migration ran"); assertEq(RambleonDB.schemaVersion, 2, "schema stamped")
  ns.InitDB()
  assertEq(ran, 1, "migration does not run twice")
  RambleonDB.schemaVersion = 99
  ns.InitDB()
  assertEq(RambleonDB.schemaVersion, 99, "data from a newer Rambleon is left alone")
  assert(ns.warnings[#ns.warnings]:find("newer Rambleon"), "and it is said")
  ns.MIGRATIONS[2] = nil; ns.SCHEMA_VERSION = 1
  RambleonDB.schemaVersion = 1; RambleonDB.migrated = nil
  local sessions = RambleonDB.sessions
  RambleonDB = nil
  ns.InitDB()
  assert(type(RambleonDB.sessions) == "table" and RambleonDB.settings.autoScreenshots == true, "a fresh table on a cold start")
  RambleonDB.sessions = sessions
end

-- A type that is not in EventTypes.lua is still a memory: recorded, shown by its name, and said once
do
  local warned = #ns.warnings
  ns.AddEvent("MYSTERY", {}); ns.AddEvent("MYSTERY", {})
  assertEq(ns.DescribeEvent(table.remove(ns.session.events)), "MYSTERY", "unknown type shows its name")
  table.remove(ns.session.events)
  assertEq(#ns.warnings, warned + 1, "unknown type warned once")
end

-- An event this client does not know is recorded, not fatal
assertEq(ns.SafeRegister(ns.eventFrame, "BOGUS_EVENT"), false, "unknown event refused")
assertEq(table.remove(ns.failedEvents), "BOGUS_EVENT", "and remembered for /ramble debug")

-- A long note is cut, not lost
assertEq(#ns.AddNote(string.rep("a", 600)).text, 500, "note limit")

-- A dungeon: a /reload inside is not a second arrival, and the loading screen out is the exit
WoW.state.inInstance = true; WoW.state.instanceType = "party"; WoW.state.instanceName = "The Deadmines"
WoW.Fire("PLAYER_ENTERING_WORLD", false, false); WoW.Advance(2)
assertEq(lastOfType("INSTANCE_ENTER").name, "The Deadmines", "entered through a loading screen")
local enters = countOfType("INSTANCE_ENTER")
relog()
assertEq(countOfType("INSTANCE_ENTER"), enters, "resuming inside does not enter again")
WoW.state.inInstance = false; WoW.state.instanceType = "none"
WoW.Fire("PLAYER_ENTERING_WORLD", false, false); WoW.Advance(2)
assertEq(lastOfType("INSTANCE_EXIT").name, "The Deadmines", "left through a loading screen")

-- The chapters reader: stays out of the pictures, keeps the published date as written, clamps its pages
_G.RambleonChapters = {
  { id = "a", slug = "rambleon-birdsong", date = "Oct 2", title = "Chapter 1", journal = "First.", startedAt = 1 },
  { id = "b", slug = "rambleon-birdsong", date = "Oct 3", title = "Chapter 2", journal = "Second.", startedAt = 2 },
}
_G.RambleonChaptersMeta = { published = "October 3, 9:14 PM" }
ns.UI.ShowChapter(99)
assertEq(ns.UI.chapterIndex, 2, "NEWER stops at the last chapter")
assert(RambleonChaptersFrame.subtitle:GetText():find("published October 3, 9:14 PM", 1, true), "published date keeps its capitals")
ns.UI.ShowChapter(-3)
assertEq(ns.UI.chapterIndex, 1, "OLDER stops at the first chapter")
assert(RambleonChaptersText:GetText():find("First.", 1, true), "first chapter shown")
WoW.Advance(5)
ns.HandleSlash("mark")
assert(not RambleonChaptersFrame:IsShown(), "chapters reader hidden for the picture")
WoW.Advance(1)
assert(RambleonChaptersFrame:IsShown(), "chapters reader back after the picture")

print("OK — " .. summary)
