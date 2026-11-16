import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Ghostwriter in Omarchy's bar. The ghost turns red while it listens and fades while dictation is off or Ghostwriter
// isn't running. A click opens its settings in Omarchy's own style; a right click opens the app. Ghostwriter writes
// its state to status.json, and the panel changes settings by editing settings.json, which Ghostwriter picks up
// within half a second.
Panel {
  id: root
  moduleName: "vultify.ghostwriter"
  ipcTarget: "vultify.ghostwriter"

  readonly property string statusPath: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state")
    + "/ghostwriter/status.json"
  readonly property string pluginDir: decodeURIComponent(Qt.resolvedUrl(".").toString().replace(/^file:\/\//, ""))

  property var status: ({})
  property var saved: ({})  // settings.json as last read or written
  property bool alive: false
  property string foundProject: ""  // from where this plugin really lives, until Ghostwriter has run once

  readonly property string project: String(status.project || foundProject)
  readonly property string settingsPath: String(status.settings || (project ? project + "/settings.json" : ""))
  readonly property string state: alive ? String(status.state || "") : "stopped"
  readonly property bool running: state !== "stopped"
  readonly property bool recording: state === "listening" || state === "locked"
  readonly property bool dictationOn: value("dictation", true)
  readonly property var hotkeys: Array.isArray(status.hotkeys) ? status.hotkeys : []
  readonly property var microphones: Array.isArray(status.microphones) ? status.microphones : []
  readonly property string defaultMicrophone: String(status.defaultMicrophone || "")
  readonly property int loweredSounds: Number(status.loweredSounds || 10)

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  // A setting as saved, else as Ghostwriter last reported it, else the fallback.
  function value(name, fallback) {
    if (saved[name] !== undefined) return saved[name]
    var current = status.values || {}
    return current[name] !== undefined ? current[name] : fallback
  }

  function change(name, newValue) {
    if (!settingsPath) return
    var next = Object.assign({}, status.values || {}, saved)
    next[name] = newValue
    saved = next
    settingsFile.setText(JSON.stringify(next, null, 2) + "\n")
  }

  function stateText() {
    if (state === "stopped") return strings.t("stateStopped")
    if (state === "starting" || state === "") return strings.t("stateStarting")
    if (!dictationOn) return strings.t("stateOff")
    if (state === "listening") return strings.t("stateListening")
    if (state === "locked") return strings.t("stateLocked")
    if (state === "working") return strings.t("stateWorking")
    return strings.t("stateReady").arg(value("hotkey", ""))
  }

  function lowerSoundsText() {
    var level = Number(value("other_sounds", loweredSounds))
    if (level === 0) return strings.t("lowerSoundsMuted")
    return strings.t("lowerSoundsDescription").arg(Commons.I18n.formatNumber(level < 100 ? level : loweredSounds))
  }

  // Run Ghostwriter from its own folder: a second copy just opens the app window of the one already running.
  function launch(trayOnly) {
    if (project.charAt(0) !== "/") return
    var argv = ["env", "-C", project, project + "/.venv/bin/python", "-m", "ghostwriter"]
    Util.execArgv(trayOnly ? argv.concat(["--tray"]) : argv)
    close()
  }

  function quit() {
    var pid = Number(status.pid)
    if (pid > 0) Util.execArgv(["kill", "-INT", String(pid)])  // the same clean stop as Ctrl+C
    close()
  }

  function checkAlive() {
    var pid = Number(status.pid)
    if (pid > 0 && status.state !== "stopped") {
      if (!aliveProc.running) aliveProc.running = true
    } else {
      alive = false
    }
  }

  FileView {
    id: statusFile
    path: root.statusPath
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      try {
        root.status = JSON.parse(text())
        root.checkAlive()
      } catch (e) {
        // Caught mid write; the next change brings the whole file.
      }
    }
    onLoadFailed: { root.status = {}; root.alive = false }
  }

  FileView {
    id: settingsFile
    path: root.settingsPath
    watchChanges: true
    atomicWrites: false  // keeps the file in place, so this watch and Ghostwriter's own keep working
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      try {
        root.saved = JSON.parse(text())
      } catch (e) {
        // Keep the last good reading.
      }
    }
    onLoadFailed: root.saved = {}
  }

  // A stopped Ghostwriter can leave its status behind after a crash, so check the process is still there.
  Process {
    id: aliveProc
    command: ["kill", "-0", String(Number(root.status.pid) || 0)]
    onExited: function(exitCode) { root.alive = exitCode === 0 }
  }

  // While Ghostwriter seems stopped, read its status again too: a watch on a file that doesn't exist yet never fires.
  Timer {
    interval: 3000
    running: true
    repeat: true
    onTriggered: root.alive ? root.checkAlive() : statusFile.reload()
  }

  // Where the plugin really lives (ghostwriter/linux/omarchy in the install), so it can start Ghostwriter before
  // Ghostwriter has ever written its status.
  Process {
    running: true
    command: ["readlink", "-f", root.pluginDir]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var path = text.trim()
        var suffix = "/ghostwriter/linux/omarchy"
        if (path.endsWith(suffix)) root.foundProject = path.slice(0, -suffix.length)
      }
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "\u{F02A0}"
    active: root.recording
    dimmed: !root.running || !root.dictationOn
    tooltipText: ""
    onPressed: function(pressedButton) {
      if (pressedButton === Qt.RightButton) root.launch(false)
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight)

    content: PanelKeyCatcher {
      anchors.fill: parent
      implicitHeight: column.implicitHeight
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: Style.space(14)

        // The ghost, what it's doing, and the switch that turns dictation on and off.
        Item {
          width: parent.width
          implicitHeight: Math.max(heroIcon.implicitHeight, heroLabels.implicitHeight, dictationSwitch.implicitHeight)

          Text {
            id: heroIcon
            textFormat: Text.PlainText
            text: "\u{F02A0}"
            color: root.recording ? root.bar.urgent : root.bar.foreground
            opacity: root.running && root.dictationOn ? 1 : 0.45
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.display
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
          }

          ToggleSwitch {
            id: dictationSwitch
            visible: root.running
            checked: root.dictationOn
            foreground: root.bar.foreground
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            onToggled: root.change("dictation", !root.dictationOn)

            PanelToolTip {
              visible: dictationSwitch.containsMouse && root.dictationOn
              text: strings.t("dictationHint").arg(root.value("hotkey", ""))
              fontFamily: root.bar.fontFamily
            }
          }

          Column {
            id: heroLabels
            anchors.left: heroIcon.right
            anchors.leftMargin: Style.space(14)
            anchors.right: parent.right
            anchors.rightMargin: dictationSwitch.visible ? dictationSwitch.width + Style.space(12) : 0
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            Text {
              textFormat: Text.PlainText
              text: strings.t("title")
              color: root.bar.foreground
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
              elide: Text.ElideRight
              width: parent.width
            }

            Text {
              textFormat: Text.PlainText
              text: root.stateText().toUpperCase()
              color: root.recording ? root.bar.urgent : Qt.darker(root.bar.foreground, 1.4)
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1.2
              elide: Text.ElideRight
              width: parent.width
            }
          }
        }

        PanelSeparator {
          foreground: root.bar.foreground
        }

        Column {
          width: parent.width
          spacing: Style.space(6)
          visible: root.settingsPath !== ""

          SettingToggle {
            label: strings.t("sounds")
            description: strings.t("soundsDescription")
            checked: root.value("sounds", true)
            onClicked: root.change("sounds", !checked)
          }

          SettingToggle {
            label: strings.t("pill")
            description: strings.t("pillDescription")
            checked: root.value("pill", true)
            onClicked: root.change("pill", !checked)
          }

          // On turns them down to Ghostwriter's default level; the app window has the others.
          SettingToggle {
            label: strings.t("lowerSounds")
            description: root.lowerSoundsText()
            checked: Number(root.value("other_sounds", root.loweredSounds)) < 100
            onClicked: root.change("other_sounds", checked ? 100 : root.loweredSounds)
          }

          SettingToggle {
            label: strings.t("history")
            description: strings.t("historyDescription")
            checked: root.value("history", true)
            onClicked: root.change("history", !checked)
          }
        }

        Column {
          width: parent.width
          spacing: Style.spacing.labelGap
          visible: root.hotkeys.length > 0

          Dropdown {
            width: parent.width
            label: strings.t("hotkey")
            fontFamily: root.bar.fontFamily
            options: root.hotkeys
            value: String(root.value("hotkey", ""))
            onChanged: function(choice) { root.change("hotkey", choice) }
          }

          // Only when there are mics to pick from; otherwise Ghostwriter records from the system's default.
          Dropdown {
            width: parent.width
            visible: root.microphones.length > 0
            label: strings.t("microphone")
            fontFamily: root.bar.fontFamily
            options: [root.defaultMicrophone].concat(root.microphones)
            value: root.value("microphone", null) || root.defaultMicrophone
            onChanged: function(choice) { root.change("microphone", choice === root.defaultMicrophone ? null : choice) }
          }
        }

        Row {
          id: actions
          width: parent.width
          spacing: Style.space(6)

          readonly property real cellWidth: root.running ? (width - spacing) / 2 : width

          Button {
            width: actions.cellWidth
            iconText: "\u{F02A0}"
            text: root.running ? strings.t("open") : strings.t("start")
            fontSize: Style.font.bodySmall
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            bordered: true
            enabled: root.project !== ""
            onClicked: root.launch(!root.running)
          }

          Button {
            visible: root.running
            width: actions.cellWidth
            iconText: "\u{F0425}"
            text: strings.t("quit")
            fontSize: Style.font.bodySmall
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            bordered: true
            onClicked: root.quit()
          }
        }
      }
    }
  }

  // One on/off row in Omarchy's style: its name and what it does, with a switch on the right.
  component SettingToggle: Toggle {
    width: parent ? parent.width : 0
    foreground: root.bar.foreground
    fontFamily: root.bar.fontFamily
  }
}
