-- Rambleon: slash commands.
local ADDON, ns = ...

local function help()
  ns.Print("commands:")
  ns.Print("  /ramble — open or close your adventure log")
  ns.Print("  /ramble status — one-line summary of tonight")
  ns.Print("  /ramble note <text> — write down what just happened")
  ns.Print("  /ramble mark — remember this moment (takes a screenshot)")
  ns.Print("  /ramble shots on|off — automatic screenshots at level ups, marks and new zones")
  ns.Print("  /ramble save — write the log to disk now (asks before reloading; logging out does it anyway)")
  ns.Print("  /ramble chapters — read past chapters (published from your Mac)")
  ns.Print("  /ramble debug — addon and client diagnostics")
  ns.Print("  /ramble dump — the last 20 events")
end

local function handle(msg)
  msg = ns.Trim(msg or "")
  local cmd, rest = msg:match("^(%S+)%s*(.-)$")
  cmd = (cmd or ""):lower()
  if cmd == "" then
    ns.UI.Toggle()
  elseif cmd == "status" then
    ns.Print(ns.Journal.StatusLine())
  elseif cmd == "note" then
    if rest == "" then
      ns.UI.PromptNote()
    else
      local ev = ns.AddNote(rest)
      if ev then ns.Print("Noted.") end
    end
  elseif cmd == "mark" then
    if ns.MarkMoment() then ns.UI.MomentRemembered() end
  elseif cmd == "shots" or cmd == "screenshots" then
    if rest == "on" then ns.SetAutoShots(true) elseif rest == "off" then ns.SetAutoShots(false) end
    ns.Print("automatic screenshots are " .. (ns.AutoShotsEnabled() and "on" or "off")
             .. " (level ups, /ramble mark, new zones; /ramble shots on|off)")
  elseif cmd == "save" or cmd == "end" then
    ns.UI.PromptEndChapter()
  elseif cmd == "debug" then
    if rest == "on" then ns.SetSetting("debug", true) elseif rest == "off" then ns.SetSetting("debug", false) end
    for _, line in ipairs(ns.DebugReport()) do ns.Print(line) end
    ns.Print("debug chatter is " .. (ns.debugEnabled and "on" or "off") .. " (/ramble debug on|off)")
  elseif cmd == "dump" then
    local s = ns.session
    if not s then ns.Print("no session") return end
    local from = math.max(1, #s.events - 19)
    for i = from, #s.events do
      local ev = s.events[i]
      ns.Print(string.format("%s  %s  [%s]", ns.FormatClock(ev.t), ns.Journal.DescribeEvent(ev), ev.type))
    end
  elseif cmd == "chapters" or cmd == "read" then
    ns.UI.ToggleChapters()
  elseif cmd == "help" then
    help()
  else
    ns.Print("unknown command '" .. cmd .. "'")
    help()
  end
end

SLASH_RAMBLEON1 = "/ramble"
SLASH_RAMBLEON2 = "/rambleon"
SlashCmdList["RAMBLEON"] = handle
ns.HandleSlash = handle

-- Keybinding entry points (see Bindings.xml)
BINDING_HEADER_RAMBLEON = "Rambleon"
BINDING_NAME_RAMBLEON_TOGGLE = "Open Adventure Log"
BINDING_NAME_RAMBLEON_MARK = "Mark Moment"
_G.Rambleon.Toggle = function() ns.UI.Toggle() end
_G.Rambleon.Mark = function() if ns.MarkMoment() then ns.UI.MomentRemembered() end end
