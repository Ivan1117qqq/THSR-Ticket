import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    objectName: 'managementDialog'
    required property var backend
    readonly property var service: backend.management
    property var record: ({})
    function showRecord(value) {service.reset(); record=value; code.text=value.code || ''; consent.checked=false; captchaInput.text=''; open()}
    title: '官網訂位核對與取消（實驗性）'
    anchors.centerIn: parent
    modal: true
    closePolicy: Popup.NoAutoClose
    width: Math.min(760,parent.width-40)
    height: Math.min(650,parent.height-40)
    Connections {target:dialog.service; function onChanged() {if(dialog.service.stage !== 'review') consent.checked=false; if(dialog.service.stage !== 'captcha') captchaInput.text=''}}
    contentItem: ColumnLayout {
        spacing: 16
        Caption {text:dialog.service.message; Accessible.name:text; Accessible.role:Accessible.StaticText}
        ProgressBar {Layout.fillWidth:true; indeterminate:true; visible:dialog.service.stage === 'working'}
        ScrollView {
            id:body; Layout.fillWidth:true; Layout.fillHeight:true; clip:true; contentWidth:availableWidth
            ColumnLayout {
                width:body.availableWidth; spacing:16
                Caption {text:'使用目前設定的取票識別碼與這筆代碼查詢。尚未取得代碼時，請先至官網查詢代碼；查無資料不會自動解除防重送。'}
                TextField {id:code; Layout.fillWidth:true; placeholderText:'八碼訂位代碼'; maximumLength:8; enabled:!dialog.service.busy; Accessible.name:'訂位代碼'; selectByMouse:true}
                AppButton {text:'開始官網核對'; enabled:!dialog.backend.running && code.text.length===8; onClicked:dialog.service.start(code.text,dialog.record.fingerprint || '',dialog.record.ticket || {})}
                Card {
                    visible:dialog.service.stage === 'captcha'; Layout.fillWidth:true; title:'輸入官網驗證碼'
                    Image {source:dialog.service.captcha; Layout.preferredWidth:220; Layout.preferredHeight:72; fillMode:Image.PreserveAspectFit; Accessible.name:'官網查詢驗證碼圖片'}
                    RowLayout {
                        TextField {id:captchaInput; maximumLength:4; placeholderText:'四碼英數字'; Accessible.name:'查詢驗證碼'; onAccepted:dialog.service.query(text)}
                        AppButton {text:'換圖'; onClicked:dialog.service.refreshCaptcha()}
                        AppButton {text:'查詢'; primary:true; enabled:captchaInput.text.length===4; onClicked:dialog.service.query(captchaInput.text)}
                    }
                }
                Card {
                    Layout.fillWidth:true; visible:!!dialog.service.snapshot.code; title:'官網核對結果'
                    Caption {text:'代碼：'+(dialog.service.snapshot.code || '')}
                    Caption {text:'狀態：'+({'unpaid':'未付款','paid':'已付款','collected':'已取票','cancelled':'已取消'}[dialog.service.snapshot.status] || '無法確認')}
                    Caption {text:dialog.service.snapshot.trip_matches ? '代碼、日期、起訖站與車次已通過核對。' : '完整行程尚未通過核對；不開放程式取消，請至官網確認。'}
                    Caption {readonly property var trip:dialog.service.snapshot.ticket || ({}); text:(trip.date || '日期未核對')+' · '+(trip.start_station || '—')+' → '+(trip.dest_station || '—')+' · 車次 '+(trip.train_id || '—')}
                    Caption {text:'核對時間：'+(dialog.service.snapshot.verified_at || '')}
                }
                Caption {visible:dialog.service.stage==='review'; text:'將取消整筆未付款訂位，釋出的座位不保證能重新訂得。已付款、已取票及無法辨識的頁面請在官網處理。'; color:'#a7532e'}
            }
        }
        CheckBox {id:consent; objectName:'cancellationConsent'; visible:dialog.service.stage==='review'; text:'我已核對代碼與完整行程，確認取消這筆官網訂位'; Accessible.name:text}
        Caption {text:'實站取消尚待驗收；無法辨識官網頁面時停止，保留原訂位及防重送紀錄。'}
        Flow {
            Layout.fillWidth:true; spacing:10
            AppButton {objectName:'syncOfficialButton'; text:'同步核對結果'; visible:dialog.service.stage==='snapshot'; enabled:dialog.service.snapshot.status==='cancelled' || (!!dialog.service.snapshot.trip_matches && ['unpaid','paid'].indexOf(dialog.service.snapshot.status)>=0); onClicked:dialog.service.sync()}
            AppButton {text:'準備取消未付款訂位'; visible:dialog.service.stage==='snapshot'; enabled:dialog.service.snapshot.status==='unpaid' && !!dialog.service.snapshot.trip_matches; onClicked:dialog.service.reviewCancel()}
            AppButton {objectName:'submitCancellationButton'; text:'確認取消官網訂位'; primary:true; visible:dialog.service.stage==='review'; enabled:consent.checked; onClicked:dialog.service.confirmCancel(consent.checked)}
            AppButton {text:dialog.service.busy ? '停止並結束工作階段' : '返回'; onClicked:{if(dialog.service.busy) dialog.service.stop(); else dialog.close()}}
        }
    }
}
