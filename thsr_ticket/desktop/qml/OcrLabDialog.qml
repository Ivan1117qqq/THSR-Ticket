import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id:dialog; objectName:'ocrLabDialog'
    required property var backend
    readonly property var service:backend.ocrLab
    title:'OCR 人工標註與模型評估'; anchors.centerIn:parent; modal:true; closePolicy:Popup.NoAutoClose
    width:Math.min(800,parent.width-40); height:Math.min(650,parent.height-40)
    Connections {target:dialog.service; function onChanged() {labelInput.text=dialog.service.sample.label || ''}}
    contentItem:ColumnLayout {
        spacing:16
        Caption {text:dialog.service.message}
        ProgressBar {visible:dialog.service.busy; indeterminate:true; Layout.fillWidth:true}
        Flow {
            Layout.fillWidth:true; spacing:10
            AppButton {text:'選擇圖片資料夾'; enabled:!dialog.backend.running; onClicked:dialog.service.chooseFolder()}
            AppButton {text:'載入標註並比較模型'; enabled:!dialog.backend.running; onClicked:dialog.service.evaluateFile(score.value)}
            AppButton {text:'匯出評估摘要'; enabled:!dialog.backend.running && !!dialog.service.result.models; onClicked:dialog.service.exportReport()}
        }
        RowLayout {
            Caption {text:'評估門檻 '+score.value.toFixed(2)}
            Slider {id:score; from:0; to:1; value:0.5; stepSize:0.05; Layout.fillWidth:true; enabled:!dialog.service.busy; Accessible.name:'OCR 評估分數門檻'}
        }
        ScrollView {
            id:body; Layout.fillWidth:true; Layout.fillHeight:true; clip:true; contentWidth:availableWidth
            ColumnLayout {
                width:body.availableWidth; spacing:16
                Card {
                    Layout.fillWidth:true; visible:!!dialog.service.sample.url; title:'人工核對正確文字'
                    Caption {text:(dialog.service.sample.name || '')+' · '+(dialog.service.sample.index || 0)+' / '+(dialog.service.sample.count || 0)+' · 已標註 '+(dialog.service.sample.labelled || 0)}
                    Image {source:dialog.service.sample.url || ''; Layout.fillWidth:true; Layout.preferredHeight:140; fillMode:Image.PreserveAspectFit; Accessible.name:'待人工核對的本機圖片'}
                    RowLayout {
                        TextField {id:labelInput; maximumLength:4; placeholderText:'人工確認四碼英數字'; Accessible.name:'人工正確標籤'; enabled:!dialog.service.busy}
                        AppButton {text:'保存標註'; enabled:!dialog.backend.running && labelInput.text.length===4; onClicked:dialog.service.saveLabel(labelInput.text)}
                        AppButton {text:'上一張'; enabled:!dialog.service.busy; onClicked:dialog.service.step(-1)}
                        AppButton {text:'下一張'; enabled:!dialog.service.busy; onClicked:dialog.service.step(1)}
                    }
                }
                Repeater {
                    model:dialog.service.result.models ? ['standard','beta'] : []
                    delegate:Card {
                        required property string modelData
                        readonly property var metrics:dialog.service.result.models[modelData]
                        Layout.fillWidth:true; title:modelData
                        Caption {text:'樣本 '+metrics.samples+' · 全碼正確 '+(metrics.exact_match_rate*100).toFixed(1)+'% · 接受比例 '+(metrics.coverage*100).toFixed(1)+'%'}
                        Caption {text:'接受後正確率 '+(metrics.accepted_accuracy===null ? '無候選' : (metrics.accepted_accuracy*100).toFixed(1)+'%')+' · 平均 '+metrics.mean_inference_ms.toFixed(1)+' ms'}
                        AppButton {text:'選用此模型'; enabled:!dialog.backend.running; onClicked:dialog.backend.setField('ocr_model',modelData)}
                    }
                }
                Caption {text:'標註必須由人獨立核對，不能把 OCR 猜測當作正確答案。評估只代表這批資料；選用模型後需儲存設定。圖片與標註只保存在本機。'}
            }
        }
        AppButton {text:dialog.service.busy ? (dialog.service.cancellable ? '取消評估／讀取' : '保存中，請等待') : '返回'; enabled:!dialog.service.busy || dialog.service.cancellable; onClicked:{if(dialog.service.busy) dialog.service.cancel(); else dialog.close()}}
    }
}
