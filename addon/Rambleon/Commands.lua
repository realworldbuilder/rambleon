-- Rambleon: slash commands. One list: what you type, what it does, and the line /ramble help prints for it.
-- A new command is one entry here.
local ADDON, ns = ...

local function onOff(rest)
  if rest == "on" then return true elseif rest == "off" then return false end
  return nil
end

local function help()
  ns.Print("commands:")
  for _, c in ipairs(ns.COMMANDS) do
    local usage = "/ramble" .. (c.name ~= "" and (" " .. c.name) or "") .. (c.args and (" " .. c.args) or "")
    local also = c.aliases and (" (also: " .. table.concat(c.aliases, ", ") .. ")") or ""
    ns.Print("  " .. usage .. " — " .. c.help .. also)
  end
end

-- name "" is the bare /ramble. fn gets whatever follows the command word.
ns.COMMANDS = {
  { name = "", help = "open or close your adventure log",
    fn = function() ns.UI.Toggle() end },
  { name = "status", help = "one-line summary of tonight",
    fn = function() ns.Print(ns.Journal.StatusLine()) end },
  { name = "note", args = "<text>", help = "write down what just happened",
    fn = function(rest)
      if rest == "" then ns.UI.PromptNote() elseif ns.AddNote(rest) then ns.Print("Noted.") end
    end },
  { name = "mark", help = "remember this moment (takes a screenshot)",
    fn = function() ns.MarkMoment() end },
  { name = "shots", aliases = { "screenshots" }, args = "on|off", help = "automatic screenshots at level ups, marks and new zones",
    fn = function(rest)
      local on = onOff(rest)
      if on ~= nil then ns.SetAutoShots(on) end
      ns.Print("automatic screenshots are " .. (ns.AutoShotsEnabled() and "on" or "off")
               .. " (level ups, /ramble mark, new zones; /ramble shots on|off)")
    end },
  { name = "chapters", aliases = { "read" }, help = "read past chapters (published from your Mac)",
    fn = function() ns.UI.ToggleChapters() end },
  { name = "save", aliases = { "end" }, help = "write the log to disk now (asks before reloading; logging out does it anyway)",
    fn = function() ns.UI.PromptEndChapter() end },
  { name = "debug", args = "[on|off]", help = "addon and client diagnostics; on|off for debug chatter",
    fn = function(rest)
      local on = onOff(rest)
      if on ~= nil then ns.SetSetting("debug", on) end
      for _, line in ipairs(ns.DebugReport()) do ns.Print(line) end
      ns.Print("debug chatter is " .. (ns.debugEnabled and "on" or "off") .. " (/ramble debug on|off)")
    end },
  { name = "dump", help = "the last 20 events",
    fn = function()
      local s = ns.session
      if not s then ns.Print("no session") return end
      for i = math.max(1, #s.events - 19), #s.events do
        local ev = s.events[i]
        ns.Print(string.format("%s  %s  [%s]", ns.FormatClock(ev.t), ns.DescribeEvent(ev), ev.type))
      end
    end },
  { name = "help", help = "this list", fn = help },
}

local byWord = {}
for _, c in ipairs(ns.COMMANDS) do
  byWord[c.name] = c
  for _, alias in ipairs(c.aliases or {}) do byWord[alias] = c end
end

local function handle(msg)
  msg = ns.Trim(msg or "")
  local word, rest = msg:match("^(%S+)%s*(.-)$")
  word = (word or ""):lower()
  local command = byWord[word]
  if not command then
    ns.Print("unknown command '" .. word .. "'")
    help()
    return
  end
  command.fn(rest or "")
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
_G.Rambleon.Mark = function() ns.MarkMoment() end
