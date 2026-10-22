-- Rambleon: every kind of event the log can hold, in one place.
-- A new thing to remember is one entry here (how it reads in the log, and the counter it bumps, if any),
-- one ns.AddEvent call where it happens (usually a handler in Events.lua), and its twin entry in the
-- companion's events.py. docs/extending.md walks through it.
local ADDON, ns = ...

local function place(ev)
  return ev.subzone or ev.zone
end

local function quest(ev)
  return '"' .. tostring(ev.title or ("quest " .. tostring(ev.questID))) .. '"'
end

-- "Gorefang (rare)": the tag the target carried, when it was one worth a word.
local function tagged(name, classification)
  if classification then return tostring(name) .. " (" .. tostring(classification) .. ")" end
  return tostring(name)
end

-- What the record says did it, when it says anything.
local function death(ev)
  local where = tostring(place(ev) or "the wilds")
  local kind = ev.killerKind
  if kind == "creature" and ev.killer then return "Slain by " .. tagged(ev.killer, ev.killerClassification) .. " in " .. where end
  if kind == "player" then return "Killed by another player in " .. where end
  if kind == "fall" then return "Fell to death in " .. where end
  if kind == "drowning" then return "Drowned in " .. where end
  if kind == "fatigue" then return "Died of fatigue in " .. where end
  return "Died in " .. where
end

local function flight(ev)
  if ev.from and ev.to then return "Flew from " .. ev.from .. " to " .. ev.to end
  if ev.to then return "Flew to " .. ev.to end
  return "Took a flight"
end

-- A line of roleplay, as a script would print it. An emote the client wrote in the second person stands as it came.
local function chat(ev)
  local who, text = tostring(ev.speaker), tostring(ev.text)
  if ev.channel == "emote" then
    if text:find("^You ") then return text end
    return who .. " " .. text
  end
  if ev.channel == "yell" then return who .. ' yells: "' .. text .. '"' end
  if ev.channel == "party" then return who .. ' (party): "' .. text .. '"' end
  return who .. ': "' .. text .. '"'
end

-- describe: a string, or a function of the event. counter: the key in session.counters that goes up by one.
ns.EVENT_TYPES = {
  SESSION_START = { describe = "Began the adventure" },
  RESUMED = { describe = "Picked the story back up" },
  SESSION_END = { describe = "Ended the chapter" },
  ZONE_ENTER = { describe = function(ev)
    if ev.subzone then return "Entered " .. ev.subzone .. " (" .. tostring(ev.zone) .. ")" end
    return "Entered " .. tostring(ev.zone)
  end },
  LEVEL_UP = { counter = "levelsGained", describe = function(ev) return "Reached Level " .. tostring(ev.level) end },
  QUEST_ACCEPTED = { counter = "questsAccepted", describe = function(ev) return "Accepted " .. quest(ev) end },
  QUEST_COMPLETED = { counter = "questsCompleted", describe = function(ev) return "Completed " .. quest(ev) end },
  QUEST_ABANDONED = { counter = "questsAbandoned", describe = function(ev) return "Abandoned " .. quest(ev) end },
  OBJECTIVE_COMPLETE = { counter = "objectivesCompleted", describe = function(ev)
    return tostring(ev.text or "Objective complete") .. (ev.title and (" — " .. ev.title) or "")
  end },
  DEATH = { counter = "deaths", describe = death },
  REVIVED = { describe = "Back among the living" },
  GROUP_JOIN = { describe = function(ev) return "Joined forces with " .. tostring(ev.name) end },
  GROUP_LEAVE = { describe = function(ev) return "Parted ways with " .. tostring(ev.name) end },
  INSTANCE_ENTER = { describe = function(ev) return "Entered " .. tostring(ev.name or "an instance") end },
  INSTANCE_EXIT = { describe = function(ev) return "Left " .. tostring(ev.name or "the instance") end },
  BOSS_KILL = { describe = function(ev) return "Defeated " .. tostring(ev.name or "a boss") end },
  HEARTH_BOUND = { describe = function(ev) return "Made " .. tostring(ev.name or place(ev) or "this place") .. " home" end },
  HEARTH_USED = { describe = function(ev) return "Hearthed home" .. (ev.to and (" to " .. ev.to) or "") end },
  FLIGHT = { describe = flight },
  FLIGHT_PATH_DISCOVERED = { describe = function(ev) return "Found the flight path at " .. tostring(ev.name or place(ev) or "this place") end },
  DISCOVERED = { counter = "discoveries", describe = function(ev) return "Discovered " .. tostring(ev.name) end },
  SPELL_LEARNED = { counter = "spellsLearned", describe = function(ev) return "Learned " .. tostring(ev.name or "a new spell") end },
  BOAT_RIDE = { describe = function(ev) return "Sailed from " .. tostring(ev.from) .. " to " .. tostring(ev.to) end },
  ACHIEVEMENT = { counter = "achievements", describe = function(ev) return "Earned achievement: " .. tostring(ev.name or ev.id) end },
  SCREENSHOT = { counter = "screenshots", describe = function(ev)
    if ev.reason == "LEVEL_UP" then return "Screenshot (Level " .. tostring(ev.level) .. ")"
    elseif ev.reason == "MARK" then return "Screenshot (marked moment)"
    elseif ev.reason == "ZONE_ENTER" then return "Screenshot (entering " .. tostring(ev.zone) .. ")"
    end
    return "Took a screenshot"
  end },
  NOTE = { counter = "notes", describe = function(ev) return '"' .. tostring(ev.text) .. '"' end },
  MARK = { counter = "marks", describe = "Marked moment" },
  FIRST_KILL = { describe = function(ev) return "First " .. tagged(ev.name, ev.classification) .. " slain" end },
  LOOT = { counter = "loot", describe = function(ev)
    return "Looted " .. tostring(ev.name) .. (ev.qualityName and (" (" .. ev.qualityName .. ")") or "")
  end },
  EQUIP = { describe = function(ev) return "Equipped " .. tostring(ev.name) end },
  CHAT = { counter = "rpLines", describe = chat },
}

-- Counters that are not "one per event": places are counted once each, kills and experience come from chat lines.
ns.EXTRA_COUNTERS = { "zonesVisited", "kills", "xpGained" }

function ns.NewCounters()
  local counters = {}
  for _, def in pairs(ns.EVENT_TYPES) do
    if def.counter then counters[def.counter] = 0 end
  end
  for _, key in ipairs(ns.EXTRA_COUNTERS) do counters[key] = 0 end
  return counters
end

function ns.DescribeEvent(ev)
  local def = ns.EVENT_TYPES[ev.type]
  if not def then return tostring(ev.type) end
  if type(def.describe) == "function" then return def.describe(ev) end
  return def.describe
end
