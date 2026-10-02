-- Offline smoke test: load Rambleon under the stub, play a scripted session, check the DB is SV-safe,
-- and write a Blizzard-format fixture for the companion's parser tests.
local here = arg[0]:match("^(.*)/[^/]*$") or "."
local addonDir = here .. "/../Rambleon"
local WoW = dofile(here .. "/wowstub.lua")

local ns = {}
local files = { "Forever.lua", "Util.lua", "Core.lua", "Session.lua", "Journal.lua", "Events.lua", "UI.lua", "Commands.lua" }
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
WoW.Advance(3)                                   -- clear the screenshot rate limit
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
WoW.state.inInstance = true; WoW.state.instanceType = "party"; WoW.state.instanceName = "Ragefire Chasm"
WoW.Fire("UPDATE_INSTANCE_INFO")
WoW.state.inInstance = false; WoW.state.instanceType = "none"
WoW.Fire("UPDATE_INSTANCE_INFO")

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

-- Write the fixture
local fixtureDir = here .. "/../../companion/tests/fixtures"
local text = WoW.SerializeSavedVariables({ "RambleonDB" })
local fh = assert(io.open(fixtureDir .. "/Rambleon_simulated.lua", "wb"))
fh:write(text); fh:close()
print(string.format("OK — %d sessions, %d events in session 1, fixture written (%d bytes)",
  #RambleonDB.sessions, #ended.events, #text))
