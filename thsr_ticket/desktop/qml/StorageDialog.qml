import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    required property var backend
    function openRecovery() { storageTabs.currentIndex = 2; open() }
    id:storageDialog; objectName:'storageDialog'; title:'資料管理'; anchors.centerIn:parent; modal:true
    width:Math.min(850, parent.width - 40); height:Math.min(650, parent.height - 40)
    closePolicy:Popup.NoAutoClose
    ColumnLayout {
        anchors.fill:parent; spacing:12
        Caption {text:backend.storage.message}
        Caption {text:backend.storage.scanSummary; visible:text !== ''}
        Flow {
            Layout.fillWidth:true; spacing:12
            Repeater {
                model:backend.storage.scanReasons
                delegate:Text {
                    required property var modelData
                    text:modelData.scope + ' · ' + modelData.label + ' ' + modelData.count
                    color:'#8a5f32'; font.pixelSize:12
                }
            }
        }
        Caption {
            visible:!!backend.storage.error.code; color:'#a33b30'
            text:(backend.storage.error.guidance || '') + '  [' + (backend.storage.error.code || '') + ']'
        }
        ProgressBar {Layout.fillWidth:true; indeterminate:true; visible:backend.storage.busy}
        RowLayout {
            TextField {id:storageAfter; placeholderText:'起日 YYYY-MM-DD'; Layout.preferredWidth:170; enabled:!backend.storage.busy}
            TextField {id:storageBefore; placeholderText:'迄日 YYYY-MM-DD'; Layout.preferredWidth:170; enabled:!backend.storage.busy}
            AppButton {text:'篩選'; enabled:!backend.storage.busy; onClicked:backend.storage.filterDates(storageAfter.text,storageBefore.text)}
            AppButton {text:'重新掃描'; enabled:!backend.storage.busy; onClicked:backend.prepareStorage()}
        }
        Caption {text:'日期依紀錄檔最後修改時間；整理僅移至本機備份，不釋放空間或取消官網訂位。'}
        TabBar {
            id:storageTabs; objectName:'storageTabs'; Layout.fillWidth:true
            padding:4; spacing:4
            background:Rectangle {radius:14; color:'white'; border.color:'#e2e8ef'}
            SegmentTab {text:'執行紀錄'}
            SegmentTab {text:'備份批次'}
            SegmentTab {text:backend.storage.hasRecovery ? '中斷復原 · 待處理' : '中斷復原'}
        }
        StackLayout {
            currentIndex:storageTabs.currentIndex; Layout.fillWidth:true; Layout.fillHeight:true
            ListView {
                clip:true; model:backend.storage.rowModel; spacing:4
                ScrollBar.vertical:ScrollBar {}
                delegate:CheckDelegate {
                    required property string recordId
                    required property string dateLabel
                    required property double recordBytes
                    required property bool chosen
                    width:ListView.view.width
                    text:dateLabel + '  ·  ' + recordBytes + ' bytes\n' + recordId
                    checked:chosen; enabled:!backend.storage.busy
                    onClicked:backend.storage.select(recordId,checked)
                }
                Label {anchors.centerIn:parent; visible:parent.count === 0; text:backend.storage.busy ? '正在讀取…' : '此範圍沒有可整理紀錄'}
            }
            ListView {
                clip:true; model:backend.storage.backups; spacing:8
                ScrollBar.vertical:ScrollBar {}
                delegate:RowLayout {
                    required property var modelData
                    width:ListView.view.width
                    Label {Layout.fillWidth:true; text:modelData.date + '  ·  ' + modelData.count + ' 筆\n' + modelData.id}
                    AppButton {text:'還原此批次'; enabled:!backend.storage.busy && !backend.storage.hasRecovery; onClicked:{restoreBatchDialog.batchId=modelData.id; restoreBatchDialog.open()}}
                }
                Label {anchors.centerIn:parent; visible:parent.count === 0; text:'沒有可還原的備份批次'}
            }
            ColumnLayout {
                Caption {text:'回復會核對每筆紀錄的位置與內容，再移回操作前位置。若兩側同名或內容改變，會停止並保留資料。'}
                ListView {
                    Layout.fillWidth:true; Layout.fillHeight:true; clip:true; spacing:12
                    model:backend.storage.recoveries
                    ScrollBar.vertical:ScrollBar {}
                    delegate:ColumnLayout {
                        required property var modelData
                        width:ListView.view.width; spacing:8
                        Label {
                            Layout.fillWidth:true; wrapMode:Text.WordWrap
                            text:(modelData.action === 'move' ? '整理中斷' : modelData.action === 'restore' ? '還原中斷' : '操作清單無法讀取')
                                 + '  ·  ' + modelData.count + ' 筆\n' + modelData.id
                        }
                        Caption {visible:!modelData.recoverable; text:'清單損壞或版本不支援，請保留兩側資料與操作清單，使用相容版本或人工協助處理。'}
                        AppButton {
                            text:'回復操作前位置'; visible:modelData.recoverable; enabled:!backend.storage.busy
                            onClicked:{recoverStorageDialog.operationId=modelData.id; recoverStorageDialog.open()}
                        }
                        Line {}
                    }
                    Label {anchors.centerIn:parent; visible:parent.count === 0; text:'沒有未完成的紀錄操作'}
                }
            }
        }
        Caption {text:backend.storage.selectionSummary; visible:storageTabs.currentIndex === 0}
        RowLayout {
            AppButton {text:'返回'; enabled:!backend.storage.busy; onClicked:storageDialog.close()}
            AppButton {text:'取消掃描'; visible:backend.storage.scanning; onClicked:backend.storage.cancel()}
            AppButton {text:'全選篩選結果'; visible:storageTabs.currentIndex === 0; enabled:!backend.storage.busy; onClicked:backend.storage.selectVisible(true)}
            AppButton {text:'清除勾選'; visible:storageTabs.currentIndex === 0; enabled:!backend.storage.busy; onClicked:backend.storage.selectVisible(false)}
            AppButton {text:'整理所選'; visible:storageTabs.currentIndex === 0; enabled:!backend.storage.busy && !backend.storage.hasRecovery && backend.storage.selectedCount > 0; onClicked:moveBatchDialog.open()}
        }
    }

    Dialog {
        id:recoverStorageDialog; objectName:'recoverStorageDialog'; property string operationId:''
        title:'確認中斷復原'; anchors.centerIn:parent; modal:true; width:470
        standardButtons:Dialog.Ok | Dialog.Cancel
        ColumnLayout {
            width:parent.width
            Caption {text:'回復這個批次到操作前位置？'}
            Caption {text:recoverStorageDialog.operationId}
            Caption {text:'程式會先核對完整批次，不覆寫同名紀錄。復原過程不更動訂位狀態或官網訂位。'}
        }
        onAccepted:backend.storage.recover(operationId)
    }
    Dialog {
        id:moveBatchDialog; title:'確認整理'; anchors.centerIn:parent; modal:true; width:430
        standardButtons:Dialog.Ok | Dialog.Cancel
        Label {text:backend.storage.selectionSummary + '\n將移至可還原備份，官網訂位不變。'}
        onAccepted:backend.storage.moveSelected()
    }
    Dialog {
        id:restoreBatchDialog; property string batchId:''; title:'確認還原'; anchors.centerIn:parent; modal:true; width:450
        standardButtons:Dialog.Ok | Dialog.Cancel
        Label {text:'還原此批次所有紀錄？\n' + restoreBatchDialog.batchId + '\n若已有同名紀錄，會停止且不覆寫。'}
        onAccepted:backend.storage.restoreBatch(batchId)
    }
}
