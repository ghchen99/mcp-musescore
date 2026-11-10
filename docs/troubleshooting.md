# Troubleshooting

[Overview](../README.md) · [Setup](setup.md) · [Tools](tools.md) · [Repeats & drum charts](drum-charts.md) · [Skills](skills.md) · [Development](development.md) · [Troubleshooting](troubleshooting.md)


## Connection Issues
- **"Not connected to MuseScore"**:
  - Ensure MuseScore is running with a score open
  - Run the MuseScore plugin (Plugins → MuseScore API Server)
  - Check that port 8765 isn't blocked by firewall

## Plugin Issues
- **Plugin not appearing**: Check the `.qml` file is in the correct plugins directory (on Ubuntu with Snap or Flatpak, see [Ubuntu](setup.md#ubuntu))
- **Plugin listed as "musescore-mcp-websocket"**: you have an older copy of the plugin without its `title`; update the `.qml` file and restart MuseScore
- **Plugin won't enable**: Restart MuseScore after placing the plugin file
- **No console output**: Run MuseScore from terminal to see debug messages
- **New plugin actions are "Unknown command"**: MuseScore is still running the old plugin. Restart MuseScore and run the plugin again
- **`go_to_measure` reports "Mesure: 1" and the next note or time signature lands in bar 1**: an older plugin selected the bar inside an undo command, where the new selection isn't readable yet, so the cursor stayed where it was. Update the `.qml` file and restart the plugin. With an old copy, `go_to_beginning_of_score` followed by `next_element` steps reach the bar instead

## Python Server Issues
- **"No server object found"**: The server object must be named `mcp`, `server`, or `app` at module level
- **WebSocket errors**: Make sure MuseScore plugin is running before starting Python server
- **Connection timeout**: The MuseScore plugin must be actively running, not just enabled
- **Claude doesn't see new tools, or reading a large score fails with "message too big"**: Claude Desktop is still running an old server process. Quit it completely and start it again, then open a new chat

## Score Files and Highlights
- **"Could not find the saved file of the score open in MuseScore"**: save the score once in MuseScore (a new score has no file yet), or pass `score_path`
- **"… is not the file of the score open in MuseScore"** or **"… has N staves and M measures, but the open score has …"**: the file edit was refused to protect the other file; nothing was changed. Save the open score and try again without `score_path`
- **Working in a part's tab** (e.g. the drum part of a full score): file edits first save that part as its own score, `<score> - <part>.mscz`, and open it in place of the full score, whose file is backed up and left unchanged
- **Opening another score while the plugin runs**: MuseScore 4 opens it in a new window, which the plugin can't reach; the plugin keeps working on the score in its own window. Tools that switch scores (`make_part_score`, the file edits) close the current score first and verify the switch
- **Undoing measure-repeat signs**: the score was reloaded, so Ctrl+Z does not reach back; use `restore_backup`
- **Highlight boxes no longer line up**: the layout changed after they were drawn; run `clear_highlights` and highlight again

## Skills
- **Upload rejected**: the ZIP must contain the folder (`musescore-drum-chart/SKILL.md`), not the files at its root, and the folder name must match the `name:` in `SKILL.md`. Package it with the command in [Installing a skill](skills.md#installing-a-skill-in-claude-desktop-or-claudeai)
- **Claude doesn't use the skill**: check it is switched on under Customize → Skills and that code execution is enabled in Settings → Capabilities; mention "drum chart" in your request
- **Claude follows old instructions**: upload the skill again after changing it

## API Limitations
- **Selection persistence**: Some operations may affect current selection
- **Measure-repeat signs**: not available to plugins, hence the [file edit](drum-charts.md#how-measure-repeat-signs-are-applied)
- **Voltas**: no dedicated plugin API; `add_volta` is experimental
