-- Rambleon: boot sequence and debug state.
local ADDON, ns = ...

_G.Rambleon = _G.Rambleon or {}     -- the keybinding entry points live here (Commands.lua); nothing else is public

ns.loaded = false
ns.enteredWorld = false

function ns.OnAddonLoaded(name)
  if name ~= ADDON or ns.loaded then return end
  ns.loaded = true
  ns.InitDB()
  ns.Debug("loaded v" .. ns.VERSION .. " (flavor " .. ns.flavorHint .. ")")
end

function ns.OnPlayerLogin()
  ns.Print("v" .. ns.VERSION .. " — type /ramble to open your adventure log.")
end

function ns.DebugReport()
  local lines = {}
  local function add(k, v) table.insert(lines, string.format("%s: %s", k, tostring(v))) end
  add("version", ns.VERSION)
  add("flavor hint", ns.flavorHint)
  local ok, v, b, d, toc = pcall(GetBuildInfo)
  if ok then add("client", string.format("%s (%s) %s toc=%s", tostring(v), tostring(b), tostring(d), tostring(toc))) end
  add("WOW_PROJECT_ID", WOW_PROJECT_ID)
  add("db restored", ns.dbRestored)
  add("db sessions", RambleonDB and RambleonDB.sessions and #RambleonDB.sessions or 0)
  local s = ns.session
  if s then
    add("session", s.id)
    add("state", s.state)
    add("events", #s.events)
    add("played", ns.FormatDuration(ns.PlayedSeconds()))
    local last = s.events[#s.events]
    if last then add("last event", last.type .. " @ " .. ns.FormatClock(last.t)) end
  else
    add("session", "none")
  end
  local loc = ns.GetLocation()
  add("zone", tostring(loc.zone) .. " / " .. tostring(loc.subzone) .. " (map " .. tostring(loc.mapID) .. ")")
  add("auto shots", string.format("%s, Screenshot(): %s, last: %s", ns.AutoShotsEnabled() and "on" or "off",
                                  type(Screenshot) == "function" and "available" or "missing", tostring(ns.shotStatus)))
  add("failed events", #ns.failedEvents > 0 and table.concat(ns.failedEvents, ", ") or "none")
  local ls = ns.lootStats or {}
  add("loot", string.format("%d chat lines, %d read, %d kept (uncommon+)", ls.lines or 0, ls.parsed or 0, ls.kept or 0))
  if ls.lastUnparsed then add("  last unread loot line", ls.lastUnparsed) end
  add("warnings", #ns.warnings)
  for i = math.max(1, #ns.warnings - 4), #ns.warnings do
    add("  warning", ns.warnings[i])
  end
  return lines
end
