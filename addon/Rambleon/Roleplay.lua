-- Rambleon: the roleplay. What was said in character around the player — /say, /emote, /yell, and the group's
-- chat when asked for — kept word for word, so a chapter can quote the night instead of only counting it.
-- Whispers, guild, trade and the numbered channels are never read. Every line goes through ns.AddEvent;
-- the Mac decides which lines were a scene.
local ADDON, ns = ...

local LINE_MAX = 255            -- the client's own limit on a chat line
local LINES_MAX = 1500          -- lines kept per session; a crowded inn says more than a night is worth
local LINE_DEDUPE = 2           -- seconds: the client can hand the same line to two events

-- Game event -> the channel the line is remembered as. "party" covers raid too: one word for the group.
ns.CHAT_EVENTS = {
  CHAT_MSG_SAY = "say", CHAT_MSG_YELL = "yell",
  CHAT_MSG_EMOTE = "emote",          -- /e bows low: the text is the deed, the sender comes separately
  CHAT_MSG_TEXT_EMOTE = "emote",     -- /bow: the text is the whole sentence, name included
  CHAT_MSG_PARTY = "party", CHAT_MSG_PARTY_LEADER = "party",
  CHAT_MSG_RAID = "party", CHAT_MSG_RAID_LEADER = "party",
}

ns.recentLines = {}

function ns.RoleplayOn() return ns.GetSetting("rpChat") end
function ns.RoleplayPartyOn() return ns.GetSetting("rpParty") end

-- "Cassidy-Moonwhisper" (name-realm; on Forever the realm slot carries the surname) -> "Cassidy", "Moonwhisper".
function ns.SplitSpeaker(sender)
  sender = ns.CleanString(sender)
  if not sender then return nil end
  local name, rest = sender:match("^([^%-]+)%-(.+)$")
  if name then return name, rest end
  return sender, nil
end

-- Out of character, by the oldest convention there is: the line sits in double brackets.
function ns.IsOOC(text)
  return text:find("^%s*%(%(") ~= nil or text:find("%)%)%s*$") ~= nil
end

local function seenLine(lineID)
  lineID = ns.Clean(lineID)
  if type(lineID) ~= "number" then return false end
  local now = GetTime()
  for id, at in pairs(ns.recentLines) do
    if now - at > 10 then ns.recentLines[id] = nil end
  end
  if ns.recentLines[lineID] and now - ns.recentLines[lineID] < LINE_DEDUPE then return true end
  ns.recentLines[lineID] = now
  return false
end

-- One line of chat from one of the channels above. `self` marks the player's own words.
function ns.RecordChat(channel, text, sender, guid, lineID)
  if not ns.RoleplayOn() then return nil end
  if channel == "party" and not ns.RoleplayPartyOn() then return nil end
  text = ns.CleanString(text)
  local speaker, surname = ns.SplitSpeaker(sender)
  if not text or not speaker then return nil end
  if seenLine(lineID) then return nil end
  local s = ns.EnsureSession()
  if not s then return nil end
  if (s.counters.rpLines or 0) >= LINES_MAX then
    s.rpDropped = (s.rpDropped or 0) + 1
    return nil
  end
  text = ns.Trim(text)
  if text == "" then return nil end
  if #text > LINE_MAX then text = text:sub(1, LINE_MAX) end
  if channel == "emote" then
    -- A built-in emote arrives as the whole sentence ("Cassidy waves at you."); keep the deed, as /e does.
    local stripped = text:match("^" .. speaker:gsub("%p", "%%%0") .. "%s+(.+)$")
    if stripped then text = stripped end
  end
  local own
  local playerGUID = ns.CleanString(ns.SafeCall(UnitGUID, "player"))
  guid = ns.CleanString(guid)
  if guid and playerGUID then
    own = guid == playerGUID
  else
    own = speaker == (s.character and s.character.name)
  end
  return ns.AddEvent("CHAT", { channel = channel, speaker = speaker, surname = surname, text = text,
                               self = own or nil, ooc = ns.IsOOC(text) or nil })
end
