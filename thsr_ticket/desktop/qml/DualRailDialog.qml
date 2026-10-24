import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: 'dualRailDialog'
    required property var backend
    readonly property var service: backend.dualRail
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(1000, parent.width - 40)
    height: Math.min(820, parent.height - 40)
    modal: true; title: '雙鐵同時訂票'; padding: 24
    background: Rectangle {radius:20; color:'#f5f8fb'; border.color:'#dce4ed'}
    onOpened: {service.refresh_record(); acknowledged.checked=false; reveal.checked=false; manualCode.text=''}
    onClosed: {reveal.checked=false; manualCode.text=''}
    component TraField: Field {backend:dialog.service; objectPrefix:'tra_'}
    contentItem: ColumnLayout {
        spacing:14
        RowLayout {
            Layout.fillWidth:true
            ColumnLayout {
                Layout.fillWidth:true; spacing:5
                Text {text:'THSR  +  TRA'; font.pixelSize:12; font.bold:true; font.letterSpacing:2; color:'#147d70'}
                Text {text:backend.form.outbound_date + '  ·  ' + backend.form.start_at; color:'#20334b'; font.pixelSize:17; font.bold:true}
                Caption {text:'共用高鐵表單的日期、啟動時間及身分證。兩邊各成功一筆後停止，不付款。'}
            }
            AppButton {objectName:'stopDualButton'; text:'全部停止'; visible:service.busy; onClicked:service.stop('')}
        }
        RowLayout {
            Layout.fillWidth:true; spacing:12
            Repeater {
                model:service.jobs
                delegate:Rectangle {
                    required property var modelData
                    Layout.fillWidth:true; implicitHeight:130; radius:14; color:modelData.operator === 'thsr' ? '#e7f3ee' : '#eaf0fc'
                    ColumnLayout {
                        anchors.fill:parent; anchors.margins:14; spacing:6
                        RowLayout {
                            Layout.fillWidth:true
                            Text {text:modelData.operator === 'thsr' ? '高鐵' : '台鐵'; color:'#20334b'; font.pixelSize:17; font.bold:true}
                            Text {text:modelData.status === 'booked' ? '● 已訂位' : modelData.status === 'manual' ? '● 等待你操作' : modelData.status === 'pending' ? '● 待核對' : ''; color:modelData.status === 'booked' ? '#147d70' : '#a66724'; font.pixelSize:12}
                            Item {Layout.fillWidth:true}
                            AppButton {text:'顯示視窗'; quiet:true; implicitHeight:30; visible:modelData.operator === 'tra' && service.busy && ['booked','failed','stopped','limit','pending','idle'].indexOf(modelData.status) < 0; onClicked:service.focusTra()}
                            AppButton {text:'停止'; quiet:true; implicitHeight:30; visible:service.busy && ['booked','failed','stopped','limit','pending','idle'].indexOf(modelData.status) < 0; onClicked:service.stop(modelData.operator)}
                        }
                        Text {text:modelData.message; color:'#52647b'; font.pixelSize:12; Layout.fillWidth:true; wrapMode:Text.WordWrap}
                        Caption {text:modelData.attempt > 0 ? '第 ' + modelData.attempt + ' 輪' : '獨立瀏覽器與訂位紀錄'}
                    }
                }
            }
        }
        ScrollView {
            id:dualScroll
            Layout.fillWidth:true; Layout.fillHeight:true; contentWidth:availableWidth; clip:true
            ColumnLayout {
                width:dualScroll.availableWidth; spacing:14
                Card {
                    Layout.fillWidth:true; title:'台鐵備案'; subtitle:'依時段時包含全部對號車種；高鐵使用原本行程。台鐵驗證及後續選車／票種可能需要在 Chrome 接手。'
                    GridLayout {
                        columns:2; columnSpacing:20; rowSpacing:14; Layout.fillWidth:true
                        TraField {fieldKey:'start_station'; label:'台鐵出發站'; options:service.stations}
                        TraField {fieldKey:'dest_station'; label:'台鐵抵達站'; options:service.stations}
                        TraField {fieldKey:'quantity'; label:'一般座票數'; numeric:true; hint:'1–9 張；優惠票種請在官網確認'}
                        TraField {fieldKey:'train_ids'; label:'偏好車次'; hint:'最多三班，以逗號分隔；留空依時段'}
                        TraField {fieldKey:'earliest_departure'; label:'最早出發'; options:service.times; timePicker:false}
                        TraField {fieldKey:'latest_departure'; label:'最晚出發'; options:service.times; timePicker:false}
                    }
                    CheckBox {id:advanced; text:'台鐵重查設定'}
                    GridLayout {
                        visible:advanced.checked; Layout.fillWidth:true; columnSpacing:20; rowSpacing:14; columns:2
                        TraField {fieldKey:'interval_seconds'; label:'無位後重查間隔（秒）'; hint:'僅官網明確回覆無位時重查'}
                        TraField {fieldKey:'max_attempts'; label:'最多查詢輪數'; numeric:true}
                        TraField {fieldKey:'network_failure_limit'; label:'送出前連線失敗上限'; numeric:true; hint:'1–100；已送出訂位不重試'}
                        TraField {fieldKey:'max_network_delay_seconds'; label:'連線退避上限（秒）'; hint:'2–3600'}
                    }
                }
                Card {
                    visible:!!service.record.status; Layout.fillWidth:true; title:'台鐵目前紀錄'
                    subtitle:service.record.status === 'booked' ? '已取得訂票代碼，請確認繳費期限；不要的車票請自行至官網取消。' : '送出結果待核對。請先至官網查詢，再保存代碼或封存本機紀錄。'
                    Caption {text:(service.record.outbound_date || '') + '  ' + (service.record.start_station || '') + ' → ' + (service.record.dest_station || '')}
                    RowLayout {
                        visible:!!service.record.booking_code; Layout.fillWidth:true
                        TextField {readOnly:true; selectByMouse:true; text:service.record.booking_code || ''; echoMode:reveal.checked ? TextInput.Normal : TextInput.Password; Layout.fillWidth:true; Accessible.name:'台鐵訂票代碼'; implicitHeight:42}
                        AppButton {text:'複製代碼'; onClicked:service.copyCode()}
                        Button {
                            id:reveal; checkable:true; objectName:'revealTraCode'; implicitWidth:44; implicitHeight:42; Accessible.name:checked ? '隱藏台鐵訂票代碼' : '顯示台鐵訂票代碼'
                            onCheckedChanged:eye.requestPaint()
                            Canvas {id:eye; anchors.centerIn:parent; width:24; height:24
                                onPaint:{let c=getContext('2d'); c.clearRect(0,0,24,24); c.strokeStyle='#52647b'; c.lineWidth=1.6; c.beginPath(); c.moveTo(2,12); c.quadraticCurveTo(12,0,22,12); c.quadraticCurveTo(12,24,2,12); c.stroke(); c.beginPath(); c.arc(12,12,3,0,2*Math.PI); c.stroke(); if(reveal.checked){c.beginPath(); c.moveTo(3,3); c.lineTo(21,21); c.stroke()}}
                            }
                        }
                    }
                    Caption {visible:!!service.record.save_failed; text:'代碼目前只保留在面板，尚未存檔。請立即複製並核對官網，再保存核對結果。'; color:'#a66724'}
                    RowLayout {
                        visible:service.record.status === 'pending'; Layout.fillWidth:true
                        TextField {id:manualCode; objectName:'traManualCode'; placeholderText:'官網確認成功後，輸入訂票代碼'; maximumLength:12; Accessible.name:'人工核對台鐵訂票代碼'; Layout.fillWidth:true; enabled:!backend.running}
                        AppButton {objectName:'confirmTraResult'; text:'保存核對結果'; enabled:!backend.running && acknowledged.checked; onClicked:service.confirmResult(manualCode.text,acknowledged.checked)}
                    }
                    CheckBox {id:acknowledged; text:'我已在台鐵官網確認這筆訂位狀態'; enabled:!backend.running}
                    RowLayout {
                        AppButton {text:'開啟台鐵訂位查詢'; onClicked:service.official()}
                        AppButton {objectName:'archiveTraButton'; text:'封存本機紀錄'; enabled:!backend.running && acknowledged.checked && service.record.status !== 'unreadable'; onClicked:archiveDialog.open()}
                    }
                }
                Card {
                    Layout.fillWidth:true
                    CheckBox {id:showEvents; text:'顯示本次進度紀錄'}
                    TextArea {visible:showEvents.checked; Layout.fillWidth:true; readOnly:true; selectByMouse:true; wrapMode:TextEdit.Wrap; text:service.events; color:'#52647b'; font.pixelSize:12}
                    AppButton {text:'開啟台鐵執行紀錄'; quiet:true; onClicked:service.openLogs()}
                }
            }
        }
        Caption {text:service.message; color:'#53716c'}
        RowLayout {
            Layout.fillWidth:true
            AppButton {text:'關閉面板'; quiet:true; onClicked:dialog.close()}
            Item {Layout.fillWidth:true}
            AppButton {objectName:'saveDualButton'; text:'儲存台鐵設定'; enabled:!backend.running; onClicked:service.save()}
            AppButton {objectName:'previewTraButton'; text:'預填檢查 · 不訂位'; enabled:!backend.running; onClicked:service.previewTra()}
            AppButton {objectName:'startTraButton'; text:'只啟動台鐵'; enabled:!backend.running; onClicked:service.startTra()}
            AppButton {objectName:'startDualButton'; text:'雙鐵同時啟動 · 不付款'; primary:true; enabled:!backend.running; onClicked:service.start()}
        }
    }
    Dialog {
        id:archiveDialog; parent:Overlay.overlay; anchors.centerIn:parent; width:420; modal:true; title:'封存台鐵本機紀錄'
        standardButtons:Dialog.Ok | Dialog.Cancel
        contentItem:Text {text:'封存後可再次訂票。官網訂位仍保留，這個操作不會取消或退票。'; wrapMode:Text.WordWrap; color:'#52647b'}
        onAccepted:if(service.archive(acknowledged.checked)) acknowledged.checked=false
    }
}
