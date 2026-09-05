-- Location link colors use the same itinerary roles as map markers.
-- Explicit roles cover unmapped fallbacks or a different activity at a town.
local data
local map = "overview"
local roles = {photo = "planned", stay = "logistics", access = "logistics",
               optional = "optional", reference = "reference"}

local function metadata(meta)
  if meta["itinerary-map"] then map = pandoc.utils.stringify(meta["itinerary-map"]) end
  local file = assert(io.open("data/itinerary.json", "r"))
  data = pandoc.json.decode(file:read("*a"))
  file:close()
  assert(data.maps[map], "Unknown itinerary-map: " .. map)
end

local function link(el)
  local role = el.attributes["data-stop-role"]
  local place = el.attributes["data-place"]
  local photo = el.attributes["data-photo"]
  assert(not (place and photo), "A link cannot be both a place and photo point")
  if not role and place then
    assert(data.places[place], "Unknown place: " .. place)
    role = roles[(data.maps[map].label_roles or {})[place] or data.places[place].role]
  elseif not role and photo then
    assert(data.photo_points[photo], "Unknown photo point: " .. photo)
    role = data.photo_points[photo].visit == "planned" and "planned" or "optional"
  end
  if role then
    assert(role == "drive" or role == "planned" or role == "optional" or role == "logistics" or role == "reference", "Invalid link role: " .. role)
    el.classes:insert("stop-link")
    el.classes:insert("stop-" .. role)
    el.attributes["data-stop-role"] = role
  end
  return el
end

return {{Meta = metadata}, {Link = link}}
