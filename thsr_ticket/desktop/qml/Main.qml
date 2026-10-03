import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    required property var backend
    visible: true
    width: 1280; height: 880
    minimumWidth: 1080; minimumHeight: 720
    title: 'Travel Desk · 高鐵訂票'
    color: '#f4f6fa'
    font.family: 'Microsoft JhengHei UI'
    font.pixelSize: 14
    property var pageTitles: ['旅程總覽', '安排新行程', '任務進度', '我的訂位', '偏好與資料']
    property var selected: null
    property bool allowClose: false
    property string pendingAction: ''
    property var filteredRecords: backend.records.filter(function(r){
        return (history.checked || r.current) &&
            (recordStatus.currentIndex === 0 || r.status === ['','booked','submission_pending','resolved','history'][recordStatus.currentIndex]) &&
            (!recordDate.text || String(r.ticket.date || '').indexOf(recordDate.text.trim()) >= 0) &&
            (!recordSearch.text || (r.code+' '+JSON.stringify(r.ticket)).toLowerCase().indexOf(recordSearch.text.trim().toLowerCase()) >= 0)
    })
    onClosing: function(close) { close.accepted = allowClose; if (!allowClose) backend.requestClose() }
    Connections {
        target: backend
        function onCloseReady() { window.allowClose = true; window.close() }
        function onConfirmRequested(action) { window.pendingAction = action; unsavedDialog.open() }
    }

    component Caption: Text { color: '#7e8ca0'; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    component Heading: Text { color: '#20334b'; font.pixelSize: 26; font.bold: true }
    component Line: Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: '#edf0f5' }
    component FormField: Field { backend: window.backend }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.preferredWidth: 218; Layout.fillHeight: true
            color: '#142b3a'
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 20; spacing: 8
                Rectangle {
                    width: 42; height: 42; radius: 12; color: '#285346'
                    Text { anchors.centerIn: parent; text: 'T'; color: '#b7f0d2'; font.pixelSize: 25; font.bold: true }
                    Layout.topMargin: 16
                }
                Text { text: 'Travel Desk'; color: 'white'; font.pixelSize: 23; font.bold: true; Layout.topMargin: 12 }
                Text { text: '高鐵旅程管理'; color: '#8ba6b7'; font.pixelSize: 12; Layout.bottomMargin: 35 }
                Repeater {
                    model: ['旅程總覽', '新增行程', '任務進度', '我的訂位', '設定']
                    delegate: Button {
                        required property int index
                        required property string modelData
                        Layout.fillWidth: true; implicitHeight: 48
                        hoverEnabled: true
                        contentItem: RowLayout {
                            spacing:12
                            NavIcon {kind:index; ink:backend.page === index ? '#c2f4dc' : '#a7b7c5'; Layout.leftMargin:12}
                            Text {
                                text: modelData; color: backend.page === index ? '#c2f4dc' : '#a7b7c5'
                                font.pixelSize: 14; font.bold: backend.page === index; Layout.fillWidth:true
                            }
                        }
                        background: Rectangle {
                            radius: 10; color: backend.page === index ? '#254a48' : parent.hovered ? '#203d4f' : 'transparent'
                            border.width: parent.activeFocus ? 1 : 0; border.color: '#79b9b0'
                        }
                        onClicked: backend.navigate(index)
                    }
                }
                Item { Layout.fillHeight: true }
                Rectangle { Layout.fillWidth: true; height: 1; color: '#294251' }
                Text { text: backend.running ? '●  任務執行中' : '●  準備就緒'; color: '#94cdb8'; font.pixelSize: 12; Layout.topMargin: 14 }
                Text { text: 'DESKTOP  /  ' + backend.version; color: '#648093'; font.pixelSize: 10; Layout.bottomMargin: 8 }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            Rectangle {
                Layout.fillWidth: true; implicitHeight: 94; color: 'white'
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 32; anchors.rightMargin: 32
                    ColumnLayout {
                        spacing: 5
                        Text { text: 'WORKSPACE  /  ' + String(backend.page + 1).padStart(2,'0'); color: '#8a98aa'; font.pixelSize: 10; font.letterSpacing: 1.5 }
                        Text { text: window.pageTitles[backend.page] + (backend.dirty ? ' · 未儲存' : ''); color: '#20334b'; font.pixelSize: 23; font.bold: true }
                    }
                    Item { Layout.fillWidth: true }
                    AppButton { text: '載入設定'; quiet: true; enabled: !backend.running; onClicked: backend.load() }
                    AppButton { text: '儲存設定'; enabled: !backend.running; onClicked: backend.save() }
                }
            }
            StackLayout {
                currentIndex: backend.page
                Layout.fillWidth: true; Layout.fillHeight: true

                ScrollView {
                    id: overview
                    clip: true; contentWidth: availableWidth
                    ColumnLayout {
                        width: overview.availableWidth; spacing: 22
                        anchors.margins: 28
                        Item { height: 6 }
                        Rectangle {
                            Layout.fillWidth: true; Layout.leftMargin: 28; Layout.rightMargin: 28; implicitHeight: 220
                            radius: 20
                            gradient: Gradient { orientation: Gradient.Horizontal; GradientStop {position:0; color:'#193e4c'} GradientStop {position:1; color:'#236a62'} }
                            ColumnLayout {
                                anchors {fill:parent; margins:28}
                                spacing: 12
                                Text { text: 'YOUR NEXT JOURNEY'; color: '#a2cfcd'; font.pixelSize: 11; font.letterSpacing: 2 }
                                Text { text: backend.form.start_station + '   →   ' + backend.form.dest_station; color:'white'; font.pixelSize: 34; font.bold: true }
                                Text { text: backend.form.outbound_date + '    ·    ' + backend.form.earliest_departure + ' — ' + backend.form.latest_departure; color:'#c3dddf'; font.pixelSize:15 }
                                Item { Layout.fillHeight:true }
                                AppButton { text:'編輯這段旅程  →'; onClicked:backend.navigate(1) }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true; Layout.leftMargin:28; Layout.rightMargin:28; spacing:18
                            Card {
                                Layout.fillWidth:true; title:'目前任務'
                                Text { text:backend.running ? '執行中' : '待命'; color:'#147d70'; font.pixelSize:28; font.bold:true }
                                Caption { text: backend.phase }
                                AppButton { text:'查看進度'; quiet:true; onClicked:backend.navigate(2) }
                            }
                            Card {
                                Layout.fillWidth:true; title:'訂位紀錄'
                                Text { text:String(backend.records.filter(function(r){return r.current}).length) + ' 筆待處理'; color:'#20334b'; font.pixelSize:28; font.bold:true }
                                Caption { text:'保留原票，封存本機紀錄後可安排下一筆。' }
                                AppButton { text:'管理我的訂位'; quiet:true; onClicked:backend.navigate(3) }
                            }
                        }
                        Caption { Layout.leftMargin:32; Layout.rightMargin:32; text:'設定行程 → 選擇查票或自動訂位 → 在我的訂位查看結果'; Layout.bottomMargin:24 }
                    }
                }

                ScrollView {
                    id: editor
                    clip:true; contentWidth:availableWidth
                    ColumnLayout {
                        width:editor.availableWidth; spacing:18
                        Item { height:6 }
                        Caption {visible:!!backend.issues.__root__; text:backend.issues.__root__ || ''; color:'#b65539'; Layout.leftMargin:28; Layout.rightMargin:28}
                        Card {
                            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28
                            title:'01  行程與時段'; subtitle:'先選擇目的地，再安排出發時間。'
                            GridLayout {
                                columns:2; columnSpacing:24; rowSpacing:20; Layout.fillWidth:true
                                FormField {fieldKey:'start_station'; label:'出發站'; options:backend.stations}
                                FormField {fieldKey:'dest_station'; label:'抵達站'; options:backend.stations}
                                FormField {fieldKey:'outbound_date'; label:'搭車日期'; calendar:true}
                                FormField {fieldKey:'class_type'; label:'車廂'; options:['標準','商務']}
                                FormField {fieldKey:'earliest_departure'; label:'最早出發'; hint:'HH:MM，例如 09:30'}
                                FormField {fieldKey:'latest_departure'; label:'最晚出發'; hint:'HH:MM，例如 18:00'}
                            }
                            AppButton {text:'交換起訖站'; quiet:true; enabled:!backend.running; onClicked:backend.swap()}
                        }
                        Card {
                            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28; title:'02  乘客與票種'
                            GridLayout {
                                columns:3; columnSpacing:18; rowSpacing:20; Layout.fillWidth:true
                                FormField {fieldKey:'adult_tickets'; label:'成人'; numeric:true}
                                FormField {fieldKey:'child_tickets'; label:'孩童'; numeric:true}
                                FormField {fieldKey:'elder_tickets'; label:'敬老'; numeric:true}
                                FormField {fieldKey:'disabled_tickets'; label:'愛心'; numeric:true}
                                FormField {fieldKey:'college_tickets'; label:'大學生'; numeric:true}
                            }
                            Line {}
                            GridLayout {
                                columns:2; columnSpacing:24; Layout.fillWidth:true
                                FormField {fieldKey:'personal_id'; label:'身分證字號'; secret:true}
                                FormField {fieldKey:'phone_num'; label:'手機'; hint:'選填'}
                            }
                        }
                        Card {
                            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28; title:'03  啟動時間'
                            FormField {fieldKey:'start_at'; label:'台灣時間'; calendar:true; hint:'YYYY-MM-DD HH:MM:SS'}
                            AppButton {text:'設為現在'; quiet:true; enabled:!backend.running; onClicked:backend.now()}
                            CheckBox {id:advanced; text:'進階設定'; font.pixelSize:14}
                            GridLayout {
                                visible:advanced.checked; columns:2; columnSpacing:24; rowSpacing:20; Layout.fillWidth:true
                                FormField {fieldKey:'train_ids'; label:'偏好車次'; hint:'逗號分隔，留空不限'}
                                FormField {fieldKey:'ocr_model'; label:'OCR 模型'; options:['standard','beta']}
                                FormField {fieldKey:'interval_seconds'; label:'重查間隔（秒）'; hint:'必須大於 0'}
                                FormField {fieldKey:'max_attempts'; label:'最多查詢輪數'; numeric:true}
                            }
                        }
                        Item {height:12}
                    }
                }

                ScrollView {
                    id: progressPage
                    clip:true; contentWidth:availableWidth
                    ColumnLayout {
                        width:progressPage.availableWidth; spacing:20
                        Item {height:8}
                        Card {
                            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28; title:'任務狀態'
                            RowLayout {
                                Layout.fillWidth:true
                                BusyIndicator {running:backend.running; visible:backend.running; implicitWidth:44; implicitHeight:44}
                                Text {text:backend.phase; font.pixelSize:24; font.bold:true; color:'#20334b'; wrapMode:Text.WordWrap; Layout.fillWidth:true}
                            }
                            Caption {text:'第 ' + backend.attempt + ' 輪查詢  /  上限 ' + backend.form.max_attempts + ' 輪'}
                            Text {visible:backend.countdown !== ''; text:backend.countdown; font.pixelSize:36; color:'#147d70'; font.bold:true}
                            Text {
                                visible:!!backend.match.train_id
                                text:'車次 ' + (backend.match.train_id || '') + '    ' + (backend.match.depart || '') + ' → ' + (backend.match.arrive || '')
                                font.pixelSize:22; color:'#147d70'; font.bold:true
                            }
                            ProgressBar {Layout.fillWidth:true; indeterminate:backend.running; value:0}
                            Caption {text:backend.form.start_station + ' → ' + backend.form.dest_station + '   ·   ' + backend.form.outbound_date}
                            RowLayout {
                                AppButton {visible:backend.running; text:'停止任務'; onClicked:backend.stop()}
                                AppButton {text:'查看訂位結果'; onClicked:backend.navigate(3)}
                            }
                        }
                        Card {
                            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28
                            CheckBox {id:showLog; text:'顯示詳細執行紀錄'}
                            TextArea {
                                visible:showLog.checked; Layout.fillWidth:true; readOnly:true
                                text:backend.log; wrapMode:TextEdit.Wrap; selectByMouse:true
                                font.family:'Consolas'; font.pixelSize:12; color:'#4c6077'
                            }
                        }
                        Item {height:12}
                    }
                }

                ScrollView {
                    id: ticketsPage
                    clip:true; contentWidth:availableWidth
                    ColumnLayout {
                        width:ticketsPage.availableWidth; spacing:16
                        Item {height:6}
                        RowLayout {
                            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28
                            CheckBox {id:history; text:'包含歷史紀錄'}
                            Item {Layout.fillWidth:true}
                            AppButton {text:'重新整理'; quiet:true; onClicked:backend.refresh()}
                            AppButton {text:'開啟高鐵官網'; onClicked:backend.official()}
                        }
                        RowLayout {
                            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28
                            TextField {id:recordSearch; placeholderText:'搜尋代碼、車次或車站'; Layout.fillWidth:true; implicitHeight:42; selectByMouse:true}
                            TextField {id:recordDate; placeholderText:'日期包含，例如 09/30'; Layout.preferredWidth:190; implicitHeight:42}
                            ComboBox {id:recordStatus; model:['全部狀態','已訂位','待確認','已人工核對','歷史紀錄']; implicitHeight:42}
                        }
                        Card {
                            visible:window.filteredRecords.length === 0
                            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28; title:'沒有符合條件的紀錄'
                            Caption {text:'成功訂位後，車次、座位與繳費期限會顯示在這裡。'}
                            AppButton {text:'安排新行程'; primary:true; onClicked:backend.navigate(1)}
                        }
                        Repeater {
                            model:window.filteredRecords
                            delegate:Card {
                                required property var modelData
                                visible:history.checked || modelData.current
                                Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28
                                title:(modelData.ticket.start_station || '行程') + '  →  ' + (modelData.ticket.dest_station || '詳情待確認')
                                RowLayout {
                                    Layout.fillWidth:true
                                    Rectangle {
                                        implicitWidth:badge.implicitWidth+24; implicitHeight:30; radius:15
                                        color:modelData.status === 'submission_pending' ? '#fff0d8' : '#e9f4ef'
                                        Text {id:badge; anchors.centerIn:parent; color:'#566e65'; font.pixelSize:12
                                            text:({'submission_pending':'結果待確認', 'booked':'已訂位', 'unreadable':'紀錄無法讀取', 'resolved':'已人工核對', 'history':'歷史紀錄'})[modelData.status] || '需要檢查'}
                                    }
                                    Item {Layout.fillWidth:true}
                                    TextEdit {readOnly:true; text:modelData.code || '尚未取得代碼'; font.pixelSize:20; font.bold:true; color:'#20334b'; selectByMouse:true}
                                }
                                Caption {text:(modelData.ticket.date || '日期未記錄') + '   ·   ' + (modelData.ticket.depart_time || '—') + '   ·   車次 ' + (modelData.ticket.train_id || '—')}
                                Line {}
                                Caption {
                                    visible:modelData.status === 'resolved'
                                    text:'人工核對：'+({'booked':'已訂位，原票保留','not_booked':'確認沒有成立訂位','cancelled':'已自行在官網取消'}[modelData.resolution] || '未記錄')+'  '+(modelData.confirmed_at || '')
                                }
                                GridLayout {
                                    columns:2; Layout.fillWidth:true; rowSpacing:12; columnSpacing:20
                                    Caption {text:'座位   ' + (modelData.ticket.seat || '—')}
                                    Caption {text:'金額   ' + (modelData.ticket.price || '—')}
                                    Caption {text:'繳費期限   ' + (modelData.ticket.payment_deadline || '—')}
                                    Caption {text:'票數   ' + (modelData.ticket.ticket_num_info || '—')}
                                }
                                RowLayout {
                                    AppButton {visible:!!modelData.code; text:'複製代碼'; onClicked:backend.copyCode(modelData.code)}
                                    AppButton {
                                        visible:modelData.current && modelData.status === 'booked'; text:'移至歷史'; enabled:!backend.running
                                        onClicked:{window.selected = modelData; archiveDialog.open()}
                                    }
                                    AppButton {
                                        visible:modelData.current && modelData.status === 'submission_pending'; text:'處理待確認'; primary:true; enabled:!backend.running
                                        onClicked:{window.selected=modelData; outcome.currentIndex=0; checkedWebsite.checked=false; confirmedCode.text=''; resolveDialog.open()}
                                    }
                                }
                            }
                        }
                        Caption {Layout.leftMargin:32; Layout.rightMargin:32; text:'紀錄來自本機，不會同步官網付款或取消狀態。移至歷史不會取消原票。'; Layout.bottomMargin:20}
                    }
                }

                ScrollView {
                    id: settingsPage
                    clip:true; contentWidth:availableWidth
                    ColumnLayout {
                        width:settingsPage.availableWidth; spacing:20
                        Item {height:8}
                        Card {
                            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28; title:'設定與資料'
                            Caption {text:'目前設定位置'}
                            TextEdit {readOnly:true; text:backend.configPath; Layout.fillWidth:true; wrapMode:Text.WrapAnywhere; color:'#30445c'; selectByMouse:true}
                            RowLayout {
                                AppButton {text:'載入設定'; enabled:!backend.running; onClicked:backend.load()}
                                AppButton {text:'另存設定'; enabled:!backend.running; onClicked:backend.saveAs()}
                                AppButton {text:'開啟資料夾'; onClicked:backend.folder()}
                            }
                            Caption {text:'載入舊設定會沿用原位置及關聯紀錄。新設定預設存放 App 使用者資料目錄。設定包含個人資料，請妥善保管。'}
                            CheckBox {
                                text:'使用 Windows 帳號保護身分證與手機'; checked:backend.protectPrivate
                                enabled:backend.protectionAvailable && !backend.running
                                onClicked:backend.setProtection(checked)
                            }
                            Caption {text:'按「儲存設定」後套用。受保護的設定需要原 Windows 帳號才能讀取；切換為明文後才適合移至其他電腦。訂位結果與備份仍需自行保管。'}
                        }
                        Card {
                            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28; title:'Travel Desk'
                            Caption {text:'版本 ' + backend.version + ' · Qt Quick 桌面版'}
                            Caption {text:'使用本機 Chrome 與 OCR。訂位完成後停止，不進行付款。'}
                            AppButton {text:'檢查執行環境'; enabled:!backend.running; onClicked:backend.checkEnvironment()}
                            Line {}
                            Caption {text:backend.updateMessage}
                            RowLayout {
                                AppButton {text:backend.updateChecking ? '檢查中…' : '檢查更新'; enabled:!backend.running && !backend.updateChecking; onClicked:backend.checkUpdates()}
                                AppButton {text:'開啟發行頁'; visible:backend.updateAvailable; onClicked:backend.releasePage()}
                            }
                        }
                        Item {height:12}
                    }
                }
            }
            Rectangle {
                visible:backend.page === 1
                Layout.fillWidth:true; implicitHeight:84; color:'white'
                RowLayout {
                    anchors.fill:parent; anchors.leftMargin:28; anchors.rightMargin:28; spacing:12
                    ColumnLayout {
                        Text {text:backend.form.start_station + ' → ' + backend.form.dest_station; color:'#20334b'; font.bold:true; font.pixelSize:16}
                        Text {text:backend.form.outbound_date + '  ·  ' + backend.form.class_type + '車廂'; color:'#8390a2'; font.pixelSize:12}
                    }
                    Item {Layout.fillWidth:true}
                    AppButton {text:'只查票'; enabled:!backend.running; onClicked:backend.start(true)}
                    AppButton {text:'自動訂位 · 不付款'; primary:true; enabled:!backend.running; onClicked:backend.start(false)}
                }
            }
            Rectangle {
                Layout.fillWidth:true; implicitHeight:Math.max(48, statusText.implicitHeight+24)
                color:backend.error ? '#fff0e8' : '#eaf2f1'
                Text {id:statusText; anchors {left:parent.left; right:recoveryButton.left; verticalCenter:parent.verticalCenter; margins:28}
                    text:backend.status; color:backend.error ? '#a7532e' : '#53716c'; font.pixelSize:12; wrapMode:Text.WordWrap}
                AppButton {id:recoveryButton; anchors.right:parent.right; anchors.rightMargin:16; anchors.verticalCenter:parent.verticalCenter
                    visible:backend.recovery !== ''; text:backend.recovery === 'records' ? '核對訂位' : backend.recovery === 'settings' ? '檢查環境' : '調整設定'
                    onClicked:backend.recover(); implicitHeight:36}
            }
        }
    }
    Dialog {
        id:unsavedDialog; title:'尚有未儲存的變更'; anchors.centerIn:parent; modal:true; width:490
        ColumnLayout {
            width:parent.width; spacing:20
            Caption {text:'請選擇是否儲存目前設定。取消會返回原畫面。'}
            RowLayout {
                AppButton {text:'取消'; onClicked:unsavedDialog.close()}
                AppButton {text:'不儲存'; onClicked:{unsavedDialog.close(); backend.confirmAction(window.pendingAction, 'discard')}}
                AppButton {text:'儲存後繼續'; primary:true; onClicked:{unsavedDialog.close(); backend.confirmAction(window.pendingAction, 'save')}}
            }
        }
    }
    Dialog {
        id:archiveDialog; title:'移至歷史'; anchors.centerIn:parent; modal:true; width:440
        standardButtons:Dialog.Ok | Dialog.Cancel
        Label {width:parent.width; wrapMode:Text.WordWrap; text:'訂位 ' + (window.selected ? window.selected.code : '') + ' 將從目前紀錄移出。官網訂位保留，完整紀錄仍可在歷史中查看。'}
        onAccepted:backend.archive(window.selected.code)
    }
    Dialog {
        id:resolveDialog; title:'核對訂位結果'; anchors.centerIn:parent; modal:true; width:490
        standardButtons:Dialog.NoButton
        ColumnLayout {
            width:parent.width; spacing:16
            Caption {text:'請先在官網確認訂位結果。不確定時請返回，避免重複訂位。'}
            AppButton {text:'開啟高鐵官網'; onClicked:backend.official()}
            ComboBox {id:outcome; Layout.fillWidth:true; model:['請選擇核對結果','已訂位，保留原票','確認沒有成立訂位','已自行在官網取消']}
            TextField {id:confirmedCode; Layout.fillWidth:true; visible:outcome.currentIndex === 1; placeholderText:'官網訂位代碼'}
            CheckBox {id:checkedWebsite; text:'我已在官網核對，確認上述結果'}
            RowLayout {
                AppButton {text:'返回'; onClicked:resolveDialog.close()}
                AppButton {
                    text:'確認並移至歷史'; primary:true
                    enabled:checkedWebsite.checked && outcome.currentIndex > 0 && (outcome.currentIndex !== 1 || confirmedCode.text.trim() !== '')
                    onClicked:{backend.resolve(window.selected.fingerprint, ['','booked','not_booked','cancelled'][outcome.currentIndex], confirmedCode.text, checkedWebsite.checked); resolveDialog.close()}
                }
            }
        }
    }
}
