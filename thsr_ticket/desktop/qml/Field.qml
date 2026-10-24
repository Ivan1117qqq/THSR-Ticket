import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: field
    required property var backend
    required property string fieldKey
    property string objectPrefix: ''
    property string label: ''
    property string hint: ''
    property var options: []
    property bool secret: false
    property bool reveal: false
    property bool calendar: false
    property bool numeric: false
    property bool timePicker: ['start_at', 'earliest_departure', 'latest_departure'].indexOf(fieldKey) >= 0
    spacing: 8
    Layout.fillWidth: true
    enabled: !backend.running
    function focusInput() {
        if (options.length > 0) combo.forceActiveFocus(Qt.TabFocusReason)
        else input.forceActiveFocus(Qt.TabFocusReason)
    }
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
            objectName: field.objectPrefix + field.fieldKey
            Accessible.name: field.label
            Accessible.description: field.hint
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
            objectName: field.objectPrefix + 'choice_' + field.fieldKey
            Accessible.name: field.label
            Accessible.description: field.hint
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
            objectName: field.objectPrefix + 'reveal_' + field.fieldKey
            visible: field.secret
            implicitWidth: 44
            horizontalPadding: 0
            text: ''
            Accessible.name: (field.reveal ? '隱藏' : '顯示') + field.label
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
            id:calendarButton
            objectName: field.objectPrefix + 'calendar_' + field.fieldKey
            visible: field.calendar; text: '日期'; horizontalPadding: 12
            Accessible.name: '選擇' + field.label
            onClicked: if(dateLoader.item) dateLoader.item.openDate(field.backend.form[field.fieldKey])
        }
        AppButton {
            objectName: field.objectPrefix + 'time_' + field.fieldKey
            visible:field.timePicker; text:'時間'; horizontalPadding:12
            Accessible.name: '選擇' + field.label + '的時間'
            onClicked:{
                let parts = (field.fieldKey === 'start_at' ? input.text.slice(11) : input.text).split(':')
                hours.value=Number(parts[0]) || 0; minutes.value=Number(parts[1]) || 0; seconds.value=Number(parts[2]) || 0
                timeDialog.open()
            }
        }
        ColumnLayout {
            visible: field.numeric
            spacing: 0
            Button {
                objectName: field.objectPrefix + 'increase_' + field.fieldKey
                Accessible.name: '增加' + field.label
                text: '+'; implicitWidth: 32; implicitHeight: 22
                onClicked: field.backend.setField(field.fieldKey, String(Number(input.text) + 1))
            }
            Button {
                objectName: field.objectPrefix + 'decrease_' + field.fieldKey
                Accessible.name: '減少' + field.label
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
        id:timeDialog; parent:Overlay.overlay; anchors.centerIn:parent; modal:true; width:390; height:225; padding:22
        background:Rectangle {color:'white'; radius:16; border.color:'#dce3ec'}
        ColumnLayout {
            anchors.fill:parent; spacing:18
            Text {text:'選擇時間'; font.pixelSize:18; color:'#20334b'}
            RowLayout {
                SpinBox {id:hours; from:0; to:23; editable:true; Layout.fillWidth:true; Accessible.name:'小時'}
                Text {text:':'}
                SpinBox {id:minutes; from:0; to:59; editable:true; Layout.fillWidth:true; Accessible.name:'分鐘'}
                SpinBox {id:seconds; visible:field.fieldKey === 'start_at'; from:0; to:59; editable:true; Layout.fillWidth:true; Accessible.name:'秒'}
            }
            AppButton {
                text:'套用時間'; primary:true; Layout.alignment:Qt.AlignRight
                onClicked:{
                    let t=String(hours.value).padStart(2,'0')+':'+String(minutes.value).padStart(2,'0')
                    if(field.fieldKey === 'start_at') t=input.text.slice(0,10)+' '+t+':'+String(seconds.value).padStart(2,'0')
                    field.backend.setField(field.fieldKey,t); timeDialog.close()
                }
            }
        }
    }
    Loader {
        id:dateLoader
        active:field.calendar
        sourceComponent:Component {
            DatePicker {
                objectName:field.objectPrefix+'datePicker_'+field.fieldKey
                titleText:field.fieldKey === 'start_at' ? '選擇啟動日期' : '選擇'+field.label
                onDateAccepted:function(value) {
                    if(field.fieldKey === 'start_at') value += ' '+(input.text.slice(11,19) || '00:00:00')
                    field.backend.setField(field.fieldKey,value)
                }
                onClosed:calendarButton.forceActiveFocus(Qt.PopupFocusReason)
            }
        }
    }
}
