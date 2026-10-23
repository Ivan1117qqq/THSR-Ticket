import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: 'templateDialog'
    required property var backend
    readonly property var service: backend.planner
    readonly property var selected: templateList.currentIndex >= 0 && templateList.currentIndex < service.templates.length ? service.templates[templateList.currentIndex] : null
    property string shownId: ''
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(820, parent.width - 48)
    height: Math.min(590, parent.height - 48)
    modal: true; title: '常用行程範本'; padding: 24
    onOpened: service.reloadTemplates()
    onSelectedChanged: {
        let identifier=selected ? selected.id : ''
        if (identifier!==shownId) {shownId=identifier; templateName.text=selected ? selected.name : ''}
    }
    background: Rectangle {radius:20; color:'#f8fafc'; border.color:'#dce3ec'}
    contentItem: ColumnLayout {
        spacing: 16
        Caption {text:'套用會更新路線、時段、票種與查詢偏好；保留目前日期、訂票人及訂位狀態。'}
        RowLayout {
            Layout.fillWidth: true
            TextField {id:templateName; objectName:'templateName'; placeholderText:'範本名稱，例如：週末返家'; Accessible.name:'範本名稱'; maximumLength:40; Layout.fillWidth:true; implicitHeight:42}
            AppButton {objectName:'saveTemplateButton'; text:'從目前行程新增'; enabled:!backend.running; onClicked:if(service.saveTemplate(templateName.text,backend.form,'')) templateList.currentIndex=service.templates.length-1}
        }
        RowLayout {
            Layout.fillWidth:true; Layout.fillHeight:true; spacing:18
            ListView {
                id:templateList; objectName:'templateList'; Layout.preferredWidth:240; Layout.fillHeight:true
                clip:true; spacing:8; model:service.templates; currentIndex:-1
                ScrollBar.vertical: ScrollBar {}
                delegate:Button {
                    required property var modelData
                    required property int index
                    width:ListView.view.width; implicitHeight:62
                    Accessible.name:modelData.name + '，' + modelData.values.start_station + '到' + modelData.values.dest_station
                    contentItem:Column {
                        spacing:5
                        Text {text:modelData.name; color:'#20334b'; font.bold:true; width:parent.width; elide:Text.ElideRight}
                        Text {text:modelData.values.start_station+' → '+modelData.values.dest_station; color:'#718398'; font.pixelSize:12}
                    }
                    background:Rectangle {radius:10; color:templateList.currentIndex===index ? '#e3f2ed' : 'white'; border.color:parent.activeFocus ? '#147d70' : '#e4eaf1'}
                    onClicked:templateList.currentIndex=index
                }
                Text {visible:templateList.count===0; text:'還沒有範本'; anchors.centerIn:parent; color:'#8390a2'}
            }
            Rectangle {
                Layout.fillWidth:true; Layout.fillHeight:true; radius:14; color:'white'; border.color:'#e4eaf1'
                ColumnLayout {
                    anchors.fill:parent; anchors.margins:20; spacing:14
                    Text {text:dialog.selected ? dialog.selected.name : '選擇一個常用行程'; color:'#20334b'; font.pixelSize:18; font.bold:true; Layout.fillWidth:true; elide:Text.ElideRight}
                    Text {text:dialog.selected ? dialog.selected.values.start_station+'  →  '+dialog.selected.values.dest_station : '也可將目前行程存為新範本'; color:'#147d70'; font.pixelSize:22; Layout.fillWidth:true; wrapMode:Text.WordWrap}
                    Caption {text:dialog.selected ? dialog.selected.values.earliest_departure+' — '+dialog.selected.values.latest_departure+' · '+dialog.selected.values.class_type+'車廂' : ''}
                    Caption {text:dialog.selected ? '成人 '+dialog.selected.values.adult_tickets+' · 孩童 '+dialog.selected.values.child_tickets+' · 敬老 '+dialog.selected.values.elder_tickets+' · 愛心 '+dialog.selected.values.disabled_tickets+' · 大學生 '+dialog.selected.values.college_tickets : ''}
                    Caption {text:dialog.selected ? '偏好車次：'+(dialog.selected.values.train_ids || '不限') : ''}
                    Item {Layout.fillHeight:true}
                    RowLayout {
                        AppButton {text:'重新命名'; enabled:!!dialog.selected && !backend.running; onClicked:service.renameTemplate(dialog.selected.id,templateName.text)}
                        AppButton {text:'複製'; enabled:!!dialog.selected && !backend.running; onClicked:service.duplicateTemplate(dialog.selected.id)}
                        AppButton {text:'移除'; quiet:true; enabled:!!dialog.selected && !backend.running; onClicked:{removeDialog.identifier=dialog.selected.id; removeDialog.open()}}
                    }
                    AppButton {text:'以目前行程更新此範本'; quiet:true; enabled:!!dialog.selected && !backend.running; onClicked:service.saveTemplate(templateName.text,backend.form,dialog.selected.id)}
                }
            }
        }
        Caption {objectName:'templateMessage'; text:service.templateMessage; visible:text!==''}
        RowLayout {
            AppButton {text:'關閉'; quiet:true; onClicked:dialog.close()}
            Item {Layout.fillWidth:true}
            AppButton {objectName:'applyTemplateButton'; text:'套用範本'; primary:true; enabled:!!dialog.selected && !backend.running; onClicked:if(service.applyTemplate(dialog.selected.id)) dialog.close()}
        }
    }
    Dialog {
        id:removeDialog; property string identifier:''; title:'移除行程範本？'
        anchors.centerIn:parent; width:360; modal:true; standardButtons:Dialog.Cancel | Dialog.Ok
        contentItem:Caption {text:'只移除這個範本，目前行程及訂位紀錄都會保留。'}
        onAccepted:if(service.deleteTemplate(identifier)) templateList.currentIndex=-1
    }
}
