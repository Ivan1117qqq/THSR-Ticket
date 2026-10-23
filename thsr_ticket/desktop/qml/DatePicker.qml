import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: picker
    property string titleText: '選擇日期'
    property int firstYear: 1900
    property int lastYear: 2199
    property int year: 2026
    property int month: 1
    property int day: 1
    property bool synchronizing: true
    readonly property string selectedDate: String(year).padStart(4, '0') + '-' +
                                          String(month).padStart(2, '0') + '-' + String(day).padStart(2, '0')
    signal dateAccepted(string value)
    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    padding: 22
    width: Math.min(440, parent.width - 32)
    height: Math.min(440, parent.height - 32)
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    onOpened: {
        setParts(year, month, day)
        yearWheel.positionViewAtIndex(yearWheel.currentIndex, Tumbler.Center)
        monthWheel.positionViewAtIndex(monthWheel.currentIndex, Tumbler.Center)
        dayWheel.positionViewAtIndex(dayWheel.currentIndex, Tumbler.Center)
        yearWheel.forceActiveFocus(Qt.PopupFocusReason)
    }
    onAboutToHide: synchronizing = true
    Component.onCompleted: setParts(year, month, day)
    background: Rectangle {color:'white'; radius:18; border.color:'#dce3ec'}

    function daysInMonth(y, m) {
        if (m === 2) return y % 400 === 0 || (y % 4 === 0 && y % 100 !== 0) ? 29 : 28
        return [4, 6, 9, 11].indexOf(m) >= 0 ? 30 : 31
    }
    function setParts(y, m, d) {
        let calendarChanged = year !== y || month !== m
        synchronizing = true
        year = Math.max(firstYear, Math.min(lastYear, y))
        month = Math.max(1, Math.min(12, m))
        day = Math.max(1, Math.min(daysInMonth(year, month), d))
        yearWheel.currentIndex = year - firstYear
        monthWheel.currentIndex = month - 1
        dayWheel.currentIndex = day - 1
        synchronizing = false
        if (calendarChanged && opened) Qt.callLater(alignDayView)
    }
    function alignDayView() {
        if (!opened || synchronizing) return
        synchronizing = true
        dayWheel.currentIndex = day - 1
        dayWheel.positionViewAtIndex(day - 1, Tumbler.Center)
        synchronizing = false
    }
    function openDate(value) {
        let match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value).slice(0, 10))
        let now = new Date()
        let y = match ? Number(match[1]) : now.getFullYear()
        let m = match ? Number(match[2]) : now.getMonth() + 1
        let d = match ? Number(match[3]) : now.getDate()
        if (y < 1 || m < 1 || m > 12 || d < 1 || d > daysInMonth(y, m)) {
            y = now.getFullYear(); m = now.getMonth() + 1; d = now.getDate()
        }
        synchronizing = true
        firstYear = Math.min(1900, y)
        lastYear = Math.max(2199, y)
        year = y; month = m; day = d
        if (opened) setParts(y, m, d)
        else open()
    }

    component DateWheel: Tumbler {
        id: wheel
        property int firstValue: 1
        property string unitLabel: ''
        readonly property int value: firstValue + Math.max(0, currentIndex)
        Layout.fillWidth: true
        Layout.preferredHeight: 210
        visibleItemCount: 5
        wrap: false
        wheelEnabled: true
        activeFocusOnTab: true
        Accessible.name: unitLabel + '：' + value
        Accessible.description: '上下拖曳、滾動或使用方向鍵選擇'
        Keys.onUpPressed: currentIndex = Math.max(0, currentIndex - 1)
        Keys.onDownPressed: currentIndex = Math.min(count - 1, currentIndex + 1)
        background: Rectangle {
            color: '#f7f9fc'; radius:12
            border.color: wheel.activeFocus ? '#45b6a6' : '#edf0f5'
            border.width: wheel.activeFocus ? 2 : 1
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left; anchors.right: parent.right; anchors.margins:5
                height: wheel.height / wheel.visibleItemCount; radius:8; color:'#e3f2ed'
            }
        }
        delegate: Text {
            required property int index
            text: String(wheel.firstValue + index).padStart(wheel.unitLabel === '年份' ? 4 : 2, '0')
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            font.pixelSize: 20
            font.bold: Math.abs(Tumbler.displacement) < 0.5
            color: Math.abs(Tumbler.displacement) < 0.5 ? '#12665d' : '#67798e'
            opacity: 1 - Math.min(0.8, Math.abs(Tumbler.displacement) / 3)
            Accessible.ignored: true
        }
    }

    contentItem: ColumnLayout {
        spacing: 14
        RowLayout {
            Layout.fillWidth: true
            Text {text:picker.titleText; font.pixelSize:18; font.bold:true; color:'#20334b'; Layout.fillWidth:true}
            Text {objectName:picker.objectName+'_preview'; text:picker.selectedDate; color:'#147d70'; font.pixelSize:14}
        }
        Caption {text:'滾動或上下拖曳，選擇年、月、日。'}
        RowLayout {
            Layout.fillWidth: true; spacing:12
            ColumnLayout {
                Layout.fillWidth: true; spacing:10
                Text {text:'年'; color:'#67798e'; Layout.alignment:Qt.AlignHCenter}
                DateWheel {
                    id:yearWheel; objectName:picker.objectName+'_year'; unitLabel:'年份'
                    firstValue:picker.firstYear; model:picker.lastYear-picker.firstYear+1
                    onCurrentIndexChanged:if(!picker.synchronizing && currentIndex>=0) picker.setParts(firstValue+currentIndex,picker.month,picker.day)
                }
            }
            ColumnLayout {
                Layout.fillWidth: true; spacing:10
                Text {text:'月'; color:'#67798e'; Layout.alignment:Qt.AlignHCenter}
                DateWheel {
                    id:monthWheel; objectName:picker.objectName+'_month'; unitLabel:'月份'; model:12
                    onCurrentIndexChanged:if(!picker.synchronizing && currentIndex>=0) picker.setParts(picker.year,firstValue+currentIndex,picker.day)
                }
            }
            ColumnLayout {
                Layout.fillWidth: true; spacing:10
                Text {text:'日'; color:'#67798e'; Layout.alignment:Qt.AlignHCenter}
                DateWheel {
                    id:dayWheel; objectName:picker.objectName+'_day'; unitLabel:'日期'
                    model:picker.daysInMonth(picker.year,picker.month)
                    onCurrentIndexChanged:if(!picker.synchronizing && currentIndex>=0) picker.setParts(picker.year,picker.month,firstValue+currentIndex)
                }
            }
        }
        Item {Layout.fillHeight:true}
        Line {}
        RowLayout {
            Layout.fillWidth: true
            AppButton {objectName:picker.objectName+'_cancel'; text:'取消'; quiet:true; onClicked:picker.close()}
            Item {Layout.fillWidth:true}
            AppButton {
                objectName:picker.objectName+'_apply'; text:'套用日期'; primary:true
                onClicked:{picker.dateAccepted(picker.selectedDate); picker.close()}
            }
        }
    }
}
