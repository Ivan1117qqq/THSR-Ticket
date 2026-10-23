import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    required property var backend
    id: editor
    objectName: "journeyPage"
    signal templatesRequested()
    function focusIssue(key) {
        var fields = {
            start_station:input_start_station,
            dest_station:input_dest_station,
            outbound_date:input_outbound_date,
            class_type:input_class_type,
            earliest_departure:input_earliest_departure,
            latest_departure:input_latest_departure,
            adult_tickets:input_adult_tickets,
            child_tickets:input_child_tickets,
            elder_tickets:input_elder_tickets,
            disabled_tickets:input_disabled_tickets,
            college_tickets:input_college_tickets,
            personal_id:input_personal_id,
            phone_num:input_phone_num,
            start_at:input_start_at,
            train_ids:input_train_ids,
            ocr_model:input_ocr_model,
            interval_seconds:input_interval_seconds,
            max_attempts:input_max_attempts,
            network_failure_limit:input_network_failure_limit,
            max_network_delay_seconds:input_max_network_delay_seconds
        }
        var target = fields[key]
        if (!target) { editor.contentItem.contentY = 0; return }
        if (['train_ids','ocr_model','interval_seconds','max_attempts','network_failure_limit','max_network_delay_seconds'].indexOf(key) >= 0) advanced.checked = true
        Qt.callLater(function() {
            target.focusInput()
            var viewport = editor.contentItem
            var point = target.mapToItem(viewport.contentItem, 0, 0)
            viewport.contentY = Math.max(0, Math.min(point.y - 16, viewport.contentHeight - viewport.height))
        })
    }
    Connections {
        target: editor.backend
        function onValidationFailed(key) { editor.focusIssue(key) }
    }

    component FormField: Field { backend: editor.backend }
    clip:true; contentWidth:availableWidth
    ColumnLayout {
        width:editor.availableWidth; spacing:18
        Item { height:6 }
        RowLayout {
            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28
            Caption {text:'快速套用常用路線，再選擇本次日期。'; Layout.fillWidth:true}
            AppButton {objectName:'journeyTemplatesButton'; text:'常用行程範本'; enabled:!backend.running; onClicked:editor.templatesRequested()}
        }
        Caption {visible:!!backend.issues.__root__; text:backend.issues.__root__ || ''; color:'#b65539'; Layout.leftMargin:28; Layout.rightMargin:28}
        Card {
            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28
            title:'01  行程與時段'; subtitle:'先選擇目的地，再安排出發時間。'
            GridLayout {
                columns:2; columnSpacing:24; rowSpacing:20; Layout.fillWidth:true
                FormField {id:input_start_station; fieldKey:'start_station'; label:'出發站'; options:backend.stations}
                FormField {id:input_dest_station; fieldKey:'dest_station'; label:'抵達站'; options:backend.stations}
                FormField {id:input_outbound_date; fieldKey:'outbound_date'; label:'搭車日期'; calendar:true}
                FormField {id:input_class_type; fieldKey:'class_type'; label:'車廂'; options:['標準','商務']}
                FormField {id:input_earliest_departure; fieldKey:'earliest_departure'; label:'最早出發'; hint:'HH:MM，例如 09:30'}
                FormField {id:input_latest_departure; fieldKey:'latest_departure'; label:'最晚出發'; hint:'HH:MM，例如 18:00'}
            }
            AppButton {text:'交換起訖站'; quiet:true; enabled:!backend.running; onClicked:backend.swap()}
        }
        Card {
            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28; title:'02  乘客與票種'
            GridLayout {
                columns:3; columnSpacing:18; rowSpacing:20; Layout.fillWidth:true
                FormField {id:input_adult_tickets; fieldKey:'adult_tickets'; label:'成人'; numeric:true}
                FormField {id:input_child_tickets; fieldKey:'child_tickets'; label:'孩童'; numeric:true}
                FormField {id:input_elder_tickets; fieldKey:'elder_tickets'; label:'敬老'; numeric:true}
                FormField {id:input_disabled_tickets; fieldKey:'disabled_tickets'; label:'愛心'; numeric:true}
                FormField {id:input_college_tickets; fieldKey:'college_tickets'; label:'大學生'; numeric:true}
            }
            Line {}
            GridLayout {
                columns:2; columnSpacing:24; Layout.fillWidth:true
                FormField {id:input_personal_id; fieldKey:'personal_id'; label:'身分證字號'; secret:true}
                FormField {id:input_phone_num; fieldKey:'phone_num'; label:'手機'; hint:'選填'}
            }
        }
        Card {
            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28; title:'03  啟動時間'
            FormField {id:input_start_at; fieldKey:'start_at'; label:'台灣時間'; calendar:true; hint:'YYYY-MM-DD HH:MM:SS'}
            AppButton {text:'設為現在'; quiet:true; enabled:!backend.running; onClicked:backend.now()}
            CheckBox {id:advanced; text:'進階設定'; font.pixelSize:14}
            GridLayout {
                visible:advanced.checked; columns:2; columnSpacing:24; rowSpacing:20; Layout.fillWidth:true
                FormField {id:input_train_ids; fieldKey:'train_ids'; label:'偏好車次'; hint:'逗號分隔，留空不限'}
                FormField {id:input_ocr_model; fieldKey:'ocr_model'; label:'OCR 模型'; options:['standard','beta']}
                FormField {id:input_interval_seconds; fieldKey:'interval_seconds'; label:'重查間隔（秒）'; hint:'必須大於 0'}
                FormField {id:input_max_attempts; fieldKey:'max_attempts'; label:'最多查詢輪數'; numeric:true}
                FormField {id:input_network_failure_limit; fieldKey:'network_failure_limit'; label:'連續網路失敗上限'; hint:'1–100，包含首次失敗'; numeric:true}
                FormField {id:input_max_network_delay_seconds; fieldKey:'max_network_delay_seconds'; label:'網路退避上限（秒）'; hint:'2–3600；不短於重查間隔'}
            }
        }
        Item {height:12}
    }
}
