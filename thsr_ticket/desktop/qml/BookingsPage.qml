import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    required property var backend
    id: ticketsPage
    objectName: "bookingsPage"
    signal cancelRequested(var record)
    signal archiveRequested(var record)
    signal resolveRequested(var record)
    property int recordPage: 0
    property string appliedSearch: ''
    readonly property int recordPageSize: 25
    readonly property var pageData: {backend.recordCount; return backend.recordPageData(history.checked,appliedSearch,recordDate.text,recordStatus.currentIndex,recordPage)}
    readonly property int filteredCount: pageData.total
    readonly property int recordPageCount: pageData.pages
    readonly property var visibleRecords: pageData.items
    onFilteredCountChanged: recordPage = Math.min(recordPage, Math.max(0, recordPageCount - 1))
    onRecordPageChanged: if (contentItem) contentItem.contentY = 0
    clip:true; contentWidth:availableWidth
    function applySearch() {searchDelay.stop(); appliedSearch=recordSearch.text; recordPage=0}
    Timer {id:searchDelay; interval:250; onTriggered:ticketsPage.applySearch()}
    ColumnLayout {
        width:ticketsPage.availableWidth; spacing:16
        Item {height:6}
        RowLayout {
            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28
            CheckBox {id:history; objectName:'includeHistoryCheck'; text:'包含歷史紀錄'; onToggled:ticketsPage.recordPage=0}
            Item {Layout.fillWidth:true}
            AppButton {text:backend.recordsLoading ? '讀取中…' : '重新整理'; quiet:true; enabled:!backend.recordsLoading; onClicked:backend.refresh()}
            AppButton {text:'開啟高鐵官網'; onClicked:backend.official()}
        }
        RowLayout {
            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28
            TextField {id:recordSearch; objectName:'bookingSearch'; placeholderText:'搜尋代碼、車次或車站'; Accessible.name:'搜尋訂位紀錄'; Layout.fillWidth:true; implicitHeight:42; selectByMouse:true; onTextChanged:if(text==='') ticketsPage.applySearch(); else searchDelay.restart(); onAccepted:ticketsPage.applySearch()}
            TextField {id:recordDate; objectName:'bookingDateFilter'; Accessible.name:'依日期篩選訂位紀錄'; placeholderText:'日期包含，例如 09/30'; Layout.preferredWidth:190; implicitHeight:42; onTextChanged:ticketsPage.recordPage=0}
            ComboBox {id:recordStatus; objectName:'bookingStatusFilter'; Accessible.name:'依狀態篩選訂位紀錄'; model:['全部狀態','已訂位','待確認','已人工核對','歷史紀錄']; implicitHeight:42; onActivated:ticketsPage.recordPage=0}
        }
        ProgressBar {Layout.fillWidth:true; indeterminate:true; visible:backend.recordsLoading; Layout.leftMargin:28; Layout.rightMargin:28}
        Caption {Layout.leftMargin:28; Layout.rightMargin:28; text:backend.recordsSummary}
        Repeater {
            model:backend.recordsReasons
            delegate:Caption {
                required property var modelData
                Layout.leftMargin:28; Layout.rightMargin:28
                text:modelData.label + '：' + modelData.count
            }
        }
        Card {
            visible:!backend.recordsLoading && ticketsPage.filteredCount === 0
            Layout.fillWidth:true; Layout.leftMargin:28; Layout.rightMargin:28; title:'沒有符合條件的紀錄'
            Caption {text:'成功訂位後，車次、座位與繳費期限會顯示在這裡。'}
            AppButton {text:'安排新行程'; primary:true; onClicked:backend.navigate(1)}
        }
        Repeater {
            objectName:'bookingCards'
            model:ticketsPage.visibleRecords
            delegate:Card {
                objectName:'recordTicketCard'
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
                Caption {visible:!!modelData.official_status; text:'官網核對：'+({'unpaid':'未付款','paid':'已付款','collected':'已取票','cancelled':'已取消'}[modelData.official_status] || '待確認')+' · '+(modelData.verified_at || '')}
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
                        visible:modelData.current && ['booked','submission_pending'].indexOf(modelData.status)>=0; text:'官網核對／取消'; enabled:!backend.running
                        onClicked:{ticketsPage.cancelRequested(modelData)}
                    }
                    AppButton {
                        visible:modelData.current && modelData.status === 'booked'; text:'移至歷史'; enabled:!backend.running
                        onClicked:{ticketsPage.archiveRequested(modelData)}
                    }
                    AppButton {
                        visible:modelData.current && modelData.status === 'submission_pending'; text:'處理待確認'; primary:true; enabled:!backend.running
                        onClicked:{ticketsPage.resolveRequested(modelData)}
                    }
                }
            }
        }
        RowLayout {
            Layout.leftMargin:32; Layout.rightMargin:32; Layout.fillWidth:true
            visible:ticketsPage.filteredCount > ticketsPage.recordPageSize
            AppButton {text:'上一頁'; enabled:ticketsPage.recordPage > 0; onClicked:ticketsPage.recordPage--}
            Caption {text:'共 ' + ticketsPage.filteredCount + ' 筆 · 第 ' + (ticketsPage.recordPage+1) + ' / ' + ticketsPage.recordPageCount + ' 頁'}
            AppButton {text:'下一頁'; enabled:ticketsPage.recordPage+1 < ticketsPage.recordPageCount; onClicked:ticketsPage.recordPage++}
        }
        Caption {Layout.leftMargin:32; Layout.rightMargin:32; text:'紀錄來自本機；使用「官網核對／取消」查詢後可保存核對結果。移至歷史不會取消原票。'; Layout.bottomMargin:20}
    }
}
