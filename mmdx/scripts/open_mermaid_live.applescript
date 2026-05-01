on run argv
  if (count of argv) is 0 then
    error "Usage: osascript open_mermaid_live.applescript <url>"
  end if

  set mermaidUrl to item 1 of argv
  open location mermaidUrl
end run
