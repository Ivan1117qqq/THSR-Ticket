import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: field
    required property var backend
    required property string fieldKey
    property string label: ''
    property string hint: ''
    property var options: []
    property bool secret: false
    property bool reveal: false
    property bool calendar: false
    property bool numeric: false
    spacing: 8
    Layout.fillWidth: true
    enabled: !backend.running
    Connections {
        target: field.backend
        function onResetSecrets() { field.reveal = false; eye.requestPaint() }
        function onChanged() { if (field.backend.running) {field.reveal = false; eye.requestPaint()} }
    }
    Text { text: field.label; color: '#52647b'; font.pixelSize: 13 }
    RowLayout {
        Layout.fillWidth: true
        spacing: 6
        TextField {
            id: input
            objectName: field.fieldKey
            visible: field.options.length === 0
            Layout.fillWidth: true
            Layout.minimumWidth: 80
            implicitHeight: 44
            text: field.backend.form[field.fieldKey] || ''
            placeholderText: field.hint
            echoMode: field.secret && !field.reveal ? TextInput.Password : TextInput.Normal
            passwordCharacter: '●'
            font.pixelSize: 14
            color: '#20334b'
            leftPadding: 12
            rightPadding: 12
            selectByMouse: true
            onTextEdited: field.backend.setField(field.fieldKey, text)
            background: Rectangle {
                color: input.enabled ? '#f9fbfd' : '#f0f3f6'
                radius: 9
                border.color: input.activeFocus ? '#147d70' : '#e2e8ef'
                border.width: input.activeFocus ? 2 : 1
            }
        }
        ComboBox {
            id: combo
            visible: field.options.length > 0
            Layout.fillWidth: true
            implicitHeight: 44
            model: field.options
            currentIndex: Math.max(0, field.options.indexOf(field.backend.form[field.fieldKey]))
            onActivated: field.backend.setField(field.fieldKey, currentText)
            font.pixelSize: 14
            background: Rectangle { radius: 9; color: '#f9fbfd'; border.color: combo.activeFocus ? '#147d70' : '#e2e8ef' }
        }
        AppButton {
            objectName: 'reveal_' + field.fieldKey
            visible: field.secret
            implicitWidth: 44
            horizontalPadding: 0
            text: ''
            Accessible.name: field.reveal ? '隱藏' : '顯示'
            ToolTip.visible: hovered
            ToolTip.text: field.reveal ? '隱藏數值' : '顯示數值'
            onClicked: { field.reveal = !field.reveal; eye.requestPaint() }
            Canvas {
                id: eye
                anchors.centerIn: parent
                width: 24; height: 24
                onPaint: {
                    let c = getContext('2d'); c.clearRect(0,0,24,24); c.strokeStyle = '#52647b'; c.lineWidth = 1.6
                    c.beginPath(); c.moveTo(2,12); c.quadraticCurveTo(12,0,22,12)
                    c.quadraticCurveTo(12,24,2,12); c.stroke()
                    c.beginPath(); c.arc(12,12,3,0,2*Math.PI); c.stroke()
                    if (field.reveal) { c.beginPath(); c.moveTo(3,3); c.lineTo(21,21); c.stroke() }
                }
            }
        }
        AppButton {
            visible: field.calendar; text: '日期'; horizontalPadding: 12
            onClicked: {
                let d = new Date(field.backend.form[field.fieldKey].slice(0,10) + 'T12:00:00')
                if (isNaN(d.getTime())) d = new Date()
                picker.year = d.getFullYear(); picker.month = d.getMonth(); picker.open()
            }
        }
        ColumnLayout {
            visible: field.numeric
            spacing: 0
            Button {
                text: '+'; implicitWidth: 32; implicitHeight: 22
                onClicked: field.backend.setField(field.fieldKey, String(Number(input.text) + 1))
            }
            Button {
                text: '-'; implicitWidth: 32; implicitHeight: 22
                onClicked: field.backend.setField(field.fieldKey, String(Math.max(0, Number(input.text) - 1)))
            }
        }
    }
    Text { visible: field.hint !== ''; text: field.hint; color: '#8b97a8'; font.pixelSize: 11 }
    Text {
        visible: !!field.backend.issues[field.fieldKey]
        text: field.backend.issues[field.fieldKey] || ''
        color: '#b65539'; font.pixelSize: 12
    }
    Popup {
        id: picker
        property int year: 2026
        property int month: 0
        parent: Overlay.overlay
        anchors.centerIn: parent
        modal: true
        width: 350; height: 360; padding: 20
        background: Rectangle { color: 'white'; radius: 16; border.color: '#dce3ec' }
        ColumnLayout {
            anchors.fill: parent
            RowLayout {
                AppButton { text: '‹'; onClicked: { if (picker.month === 0) {picker.month = 11; picker.year--} else picker.month-- } }
                Text { text: picker.year + ' / ' + (picker.month + 1); Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
                AppButton { text: '›'; onClicked: { if (picker.month === 11) {picker.month = 0; picker.year++} else picker.month++ } }
            }
            DayOfWeekRow { locale: Qt.locale('zh_TW'); Layout.fillWidth: true }
            MonthGrid {
                month: picker.month; year: picker.year; locale: Qt.locale('zh_TW')
                Layout.fillWidth: true; Layout.fillHeight: true
                onClicked: function(date) {
                    let value = Qt.formatDate(date, 'yyyy-MM-dd')
                    if (field.fieldKey === 'start_at') value += ' ' + (input.text.slice(11,19) || '00:00:00')
                    field.backend.setField(field.fieldKey, value); picker.close()
                }
            }
        }
    }
}
