local function header_text(tbl, index)
  local row = tbl.head.rows[1]
  if not row or not row.cells[index] then
    return ""
  end
  return pandoc.utils.stringify(row.cells[index].contents)
end

-- Tag timetable tables so mobile CSS can turn each row into a readable card.
function Table(tbl)
  if FORMAT:match("html") then
    local classes = {"table-scroll"}
    local label = "可横向滚动的表格"
    if header_text(tbl, 1) == "时间" and header_text(tbl, 2) == "安排" then
      table.insert(classes, "schedule-scroll")
      label = "逐日时间安排"
    end
    return pandoc.Div({tbl}, pandoc.Attr("", classes, {
      role = "region", ["aria-label"] = label, tabindex = "0"
    }))
  end
end
