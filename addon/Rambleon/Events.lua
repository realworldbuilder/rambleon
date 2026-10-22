-- Rambleon: game event wiring. Passive only. Registrations are pcall-guarded because
-- the Forever client throws on unknown events.
local ADDON, ns = ...

local frame = CreateFrame("Frame", "RambleonEventFrame")
ns.eventFrame = frame
local handlers = {}

local ZONE_DEBOUNCE = 1.5
local DEATH_ECHO = 30      -- seconds: build 70009 fires PLAYER_DEAD twice per death, one to four seconds apart
local zoneToken = 0

local function scheduleZoneCheck()
  zoneToken = zoneToken + 1
  local token = zoneToken
  if C_Timer and C_Timer.After then
    C_Timer.After(ZONE_DEBOUNCE, function()
      if token == zoneToken then ns.NoteZoneChange(false) end
    end)
  else
    ns.NoteZoneChange(false)
  end
end

local function checkInstance()
  local inInstance, instanceType = ns.SafeCall(IsInInstance)
  inInstance = inInstance and true or false
  local was = ns.inInstance or false       -- the first look of a login counts as "was outside"
  ns.inInstance = inInstance
  if inInstance == was then return end
  if inInstance then
    ns.instanceName = ns.CleanString((ns.SafeCall(GetInstanceInfo)))
    ns.AddEvent("INSTANCE_ENTER", { name = ns.instanceName, instanceType = ns.CleanString(instanceType) })
  else
    ns.AddEvent("INSTANCE_EXIT", { name = ns.instanceName })
    ns.instanceName = nil
  end
end

local function questTitle(questID)
  if not questID then return nil end
  local title = ns.questTitles[questID]
  if title then return title end
  if C_QuestLog and C_QuestLog.GetTitleForQuestID then
    title = ns.CleanString(ns.SafeCall(C_QuestLog.GetTitleForQuestID, questID))
  end
  if not title and C_QuestLog and C_QuestLog.GetQuestInfo then
    title = ns.CleanString(ns.SafeCall(C_QuestLog.GetQuestInfo, questID))
  end
  if title then ns.questTitles[questID] = title end
  return title
end

handlers.ADDON_LOADED = function(name)
  ns.OnAddonLoaded(name)
end

handlers.PLAYER_LOGIN = function()
  ns.OnPlayerLogin()
end

local objectiveToken = 0
local function scheduleObjectiveScan()
  objectiveToken = objectiveToken + 1
  local token = objectiveToken
  if C_Timer and C_Timer.After then
    C_Timer.After(1, function() if token == objectiveToken then ns.ScanObjectives() end end)
  else
    ns.ScanObjectives()
  end
end

handlers.PLAYER_ENTERING_WORLD = function(isLogin, isReload)
  if not ns.loaded then return end
  if not ns.enteredWorld then
    ns.enteredWorld = true
    ns.StartSession()
    ns.StartHeartbeat()
  end
  ns.SeedXP()
  if not ns.equipSeeded then ns.SeedEquipment() end
  checkInstance()
  scheduleZoneCheck()
  ns.UpdateRoster()
  scheduleObjectiveScan()
end

handlers.CHAT_MSG_COMBAT_XP_GAIN = function(text)
  ns.RecordKillFromChat(text)
end

handlers.CHAT_MSG_LOOT = function(text)
  ns.RecordLootFromChat(text)
end

handlers.PLAYER_EQUIPMENT_CHANGED = function(slot, hasItem)
  if hasItem then ns.RecordEquip(slot) end
end

handlers.PLAYER_XP_UPDATE = function(unit)
  if unit == nil or unit == "player" then ns.UpdateXP() end
end

handlers.UNIT_QUEST_LOG_CHANGED = function(unit)
  if unit == nil or unit == "player" then scheduleObjectiveScan() end
end

handlers.QUEST_LOG_UPDATE = function()
  scheduleObjectiveScan()
end

handlers.PLAYER_LOGOUT = function()
  ns.SuspendSession()
end

handlers.ZONE_CHANGED_NEW_AREA = scheduleZoneCheck
handlers.ZONE_CHANGED = scheduleZoneCheck
handlers.ZONE_CHANGED_INDOORS = scheduleZoneCheck

handlers.PLAYER_LEVEL_UP = function(level)
  local s = ns.EnsureSession()
  if not s then return end
  level = ns.Clean(level) or ns.Clean(ns.SafeCall(UnitLevel, "player"))
  -- What tipped it: the quest, kill or discovery a moment before; or the one a moment after (NoteCause fills it in).
  local cause = ns.RecentCause()
  local ev = ns.AddEvent("LEVEL_UP", { level = level, cause = cause, money = ns.Clean(ns.SafeCall(GetMoney)) })
  ns.pendingLevelUp = (ev and not cause) and { ev = ev, at = GetTime() } or nil
  if level then s.character.endLevel = level end
  ns.UpdateXP()
  ns.TakeScreenshot("LEVEL_UP", { level = level }, 1.0)   -- a second later the level-up glow is on screen
end

handlers.QUEST_ACCEPTED = function(a, b)
  if not ns.EnsureSession() then return end
  local questID = ns.Clean(b) or ns.Clean(a)   -- retail: (questID); classic: (questLogIndex, questID)
  if type(questID) ~= "number" then return end
  local ev = ns.AddEvent("QUEST_ACCEPTED", { questID = questID, title = questTitle(questID) })
  if ev and not ev.title and C_Timer and C_Timer.After then
    C_Timer.After(1, function()
      local title = questTitle(questID)
      if title then ev.title = title; ns.dirty = true end
    end)
  end
end

handlers.QUEST_TURNED_IN = function(questID, xp, money)
  if not ns.EnsureSession() then return end
  questID = ns.Clean(questID)
  if type(questID) ~= "number" then return end
  ns.turnedIn[questID] = true
  ns.AddEvent("QUEST_COMPLETED", { questID = questID, title = questTitle(questID),
                                   xp = ns.Clean(xp), money = ns.Clean(money) })
  ns.NoteCause("quest")
end

-- A quest leaves the log when it is handed in and when it is abandoned, and the client does not promise
-- which of QUEST_REMOVED and QUEST_TURNED_IN comes first. Wait a moment, then see which it was.
-- Only quests whose title we already know: the client also removes hidden bookkeeping quests.
handlers.QUEST_REMOVED = function(questID)
  questID = ns.Clean(questID)
  if type(questID) ~= "number" then return end
  local function settle()
    if ns.turnedIn[questID] or not ns.questTitles[questID] then return end
    if not ns.EnsureSession() then return end
    ns.AddEvent("QUEST_ABANDONED", { questID = questID, title = ns.questTitles[questID] })
  end
  if C_Timer and C_Timer.After then C_Timer.After(1, settle) else settle() end
end

-- The innkeeper made this place home.
handlers.HEARTHSTONE_BOUND = function()
  if not ns.EnsureSession() then return end
  local name = ns.CleanString((ns.SafeCall(GetBindLocation)))
  if name then ns.AddEvent("HEARTH_BOUND", { name = name }) end
end

-- A dungeon or raid boss went down (not the combat log: the encounter's own end event).
handlers.ENCOUNTER_END = function(encounterID, name, difficultyID, groupSize, success)
  if ns.Clean(success) ~= 1 or not ns.EnsureSession() then return end
  ns.AddEvent("BOSS_KILL", { name = ns.CleanString(name), encounterID = ns.Clean(encounterID) })
end

handlers.PLAYER_DEAD = function()
  if not ns.EnsureSession() then return end
  local now = ns.Now()
  -- One death, one event: the client repeats PLAYER_DEAD a few seconds after the first (verified 2026-10-01,
  -- every death recorded twice since build 70009). A second within DEATH_ECHO is the same death.
  if ns.lastDeathAt and now - ns.lastDeathAt < DEATH_ECHO then return end
  if ns.SafeCall(UnitIsFeignDeath, "player") then return end
  ns.isDead = true
  ns.lastDeathAt = now
  ns.AddEvent("DEATH", ns.DeathFields())
end

local function maybeRevived()
  if not ns.isDead then return end
  local deadOrGhost = ns.SafeCall(UnitIsDeadOrGhost, "player")
  if not deadOrGhost then
    ns.isDead = false
    ns.AddEvent("REVIVED", {})
  end
end
handlers.PLAYER_UNGHOST = maybeRevived
handlers.PLAYER_ALIVE = maybeRevived

handlers.GROUP_ROSTER_UPDATE = function()
  ns.UpdateRoster()
end

-- What you are fighting (Capture.lua keeps it for the kill line and the death)
handlers.PLAYER_TARGET_CHANGED = function() ns.NoteUnit("target") end
handlers.NAME_PLATE_UNIT_ADDED = function(unit) ns.NoteUnit(unit) end

-- Breath and fatigue bars: a death while one is empty was a drowning
handlers.MIRROR_TIMER_START = function(...) ns.OnMirrorTimerStart(...) end
handlers.MIRROR_TIMER_STOP = function(timer) ns.OnMirrorTimerStop(timer) end

-- Own casts: the hearthstone (registered for the player only, see unitEvents below)
handlers.UNIT_SPELLCAST_SUCCEEDED = function(unit, castGUID, spellID) ns.OnSpellcastSucceeded(unit, castGUID, spellID) end

-- "Discovered X", "New flight path discovered!", "You have learned a new spell: X." arrive on both of these
handlers.UI_INFO_MESSAGE = function(_, text) ns.ReadInfoMessage(text) end
handlers.CHAT_MSG_SYSTEM = function(text) ns.ReadInfoMessage(text) end

-- A trainer, a book or a level taught something
handlers.LEARNED_SPELL_IN_TAB = function(spellID) ns.RecordSpellLearned(spellID) end
handlers.LEARNED_SPELL_IN_SKILL_LINE = function(spellID) ns.RecordSpellLearned(spellID) end

-- What was said around the player (Roleplay.lua): the line, who said it, the client's line id and the sender's guid
for event, channel in pairs(ns.CHAT_EVENTS) do
  handlers[event] = function(text, sender, _, _, _, _, _, _, _, _, lineID, guid)
    ns.RecordChat(channel, text, sender, guid, lineID)
  end
end

handlers.UPDATE_INSTANCE_INFO = function()
  if ns.enteredWorld then checkInstance() end
end

handlers.ACHIEVEMENT_EARNED = function(achievementID)
  if not ns.EnsureSession() then return end
  local id = ns.Clean(achievementID)
  local name
  if GetAchievementInfo then
    local _, n = ns.SafeCall(GetAchievementInfo, id)
    name = ns.CleanString(n)
  end
  ns.AddEvent("ACHIEVEMENT", { id = id, name = name })
end

handlers.SCREENSHOT_SUCCEEDED = function()
  if not ns.EnsureSession() then return end
  local p = ns.ConsumePendingShot()
  if p then
    ns.shotStatus = "ok"
    ns.AddEvent("SCREENSHOT", { reason = p.reason, auto = true, level = p.level, zone = p.zone, subzone = p.subzone })
  else
    ns.AddEvent("SCREENSHOT", { reason = "MANUAL" })
  end
end

handlers.SCREENSHOT_FAILED = function()
  ns.RestoreUIAfterShot()
  local p = ns.pendingShot
  ns.pendingShot = nil
  if p then
    ns.shotStatus = "failed"
    ns.Warn("automatic screenshot failed (" .. tostring(p.reason) .. ")")
  end
end

frame:SetScript("OnEvent", function(self, event, ...)
  local h = handlers[event]
  if h then
    local ok, err = pcall(h, ...)
    if not ok then ns.Warn(event .. ": " .. tostring(err)) end
  end
end)

local unitEvents = { UNIT_SPELLCAST_SUCCEEDED = "player" }   -- filtered to one unit where the client allows it
for event in pairs(handlers) do
  if unitEvents[event] then
    ns.SafeRegisterUnit(frame, event, unitEvents[event])
  else
    ns.SafeRegister(frame, event)
  end
end
