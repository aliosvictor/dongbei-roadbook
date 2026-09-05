local function header_text(tbl, index)
  local row = tbl.head.rows[1]
  if not row or not row.cells[index] then
    return ""
  end
  return pandoc.utils.stringify(row.cells[index].contents)
end

local function add_mobile_labels(tbl, headers)
  for _, body in ipairs(tbl.bodies) do
    for _, row in ipairs(body.body) do
      for index, cell in ipairs(row.cells) do
        cell.attr.attributes["data-label"] = headers[index] or ""
        -- Quarto's simple-table renderer can drop cell attributes. A real label
        -- survives both rendering paths; hide it from assistive technology,
        -- which already receives the semantic table headers.
        cell.contents = {
          pandoc.Div({pandoc.Plain({pandoc.Str(headers[index] or "")})},
            pandoc.Attr("", {"cell-label"}, {["aria-hidden"] = "true"})),
          pandoc.Div(cell.contents, pandoc.Attr("", {"cell-content"}))
        }
      end
    end
  end
end

-- Tag tables by structure so narrow screens can use readable cards instead of
-- squeezing columns or hiding information beyond the viewport.
function Table(tbl)
  if FORMAT:match("html") then
    local classes = {"table-scroll"}
    local label = "可横向滚动的表格"
    if header_text(tbl, 1) == "时间" and header_text(tbl, 2) == "安排" then
      table.insert(classes, "schedule-scroll")
      label = "逐日时间安排"
    else
      local headers = {}
      for index = 1, #tbl.colspecs do
        headers[index] = header_text(tbl, index)
      end
      add_mobile_labels(tbl, headers)
      table.insert(classes, "compact-scroll")
      label = "窄屏以卡片显示的表格"
    end
    return pandoc.Div({tbl}, pandoc.Attr("", classes, {
      role = "region", ["aria-label"] = label, tabindex = "0"
    }))
  end
end
