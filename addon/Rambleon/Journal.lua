-- Rambleon: derived, human-readable views of the current session (UI, /ramble status, /ramble dump).
local ADDON, ns = ...
ns.Journal = {}
local J = ns.Journal

J.DescribeEvent = ns.DescribeEvent     -- what each event type reads like: EventTypes.lua

function J.RecentEvents(n)
  local s = ns.session
  local out = {}
  if not s then return out end
  for i = #s.events, 1, -1 do
    local ev = s.events[i]
    if ev.type ~= "RESUMED" then table.insert(out, 1, ev) end
    if #out >= n then break end
  end
  return out
end

function J.Stats()
  local s = ns.session
  if not s then return nil end
  local c = s.counters
  local loc = ns.GetLocation()
  return {
    played = ns.PlayedSeconds(),
    area = loc.subzone or loc.zone or "—",
    zone = loc.zone,
    level = ns.Clean(ns.SafeCall(UnitLevel, "player")) or s.character.endLevel or "?",
    questsCompleted = c.questsCompleted or 0,
    questsAccepted = c.questsAccepted or 0,
    places = #s.zones,
    deaths = c.deaths or 0,
    people = #s.people,
    kills = c.kills or 0,
    loot = c.loot or 0,
    xp = c.xpGained or 0,
    notes = c.notes or 0,
    marks = c.marks or 0,
    levelsGained = c.levelsGained or 0,
  }
end

function J.PeopleSummary()
  local s = ns.session
  local out = {}
  if not s then return out end
  local now = GetTime()
  for _, p in ipairs(s.people) do
    local secs = p.seconds or 0
    local g = ns.currentGroup[p.name]
    if g then secs = secs + (now - g.since) end
    table.insert(out, { name = p.name, class = p.class, minutes = math.floor(secs / 60 + 0.5) })
  end
  table.sort(out, function(a, b) return a.minutes > b.minutes end)
  return out
end

function J.StatusLine()
  local st = J.Stats()
  if not st then return "no session yet" end
  return string.format("%s in %s — Lv %s · %d quests · %d places · %d kills · %d deaths · %d people · %d notes",
    ns.FormatDuration(st.played), tostring(st.area), tostring(st.level), st.questsCompleted, st.places,
    st.kills, st.deaths, st.people, st.notes + st.marks)
end
