import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: actions
    objectName: 'bookingActions'
    required property var backend
    property var selected: null
    function showCancellation(record) {
        selected = record
        cancellationConfirmed.checked = false
        cancellationDialog.open()
    }
    function showArchive(record) { selected = record; archiveDialog.open() }
    function showResolution(record) {
        selected = record
        outcome.currentIndex = 0
        checkedWebsite.checked = false
        confirmedCode.text = ''
        resolveDialog.open()
    }
    Dialog {
        id:cancellationDialog; objectName:'cancellationDialog'; title:'取消官網訂位'; anchors.centerIn:parent; modal:true; width:550
        ColumnLayout {
            width:parent.width; spacing:16
            Label {text:'訂位代碼：' + (actions.selected ? actions.selected.code : ''); font.bold:true}
            Caption {text:actions.selected ? [actions.selected.ticket.date || '', actions.selected.ticket.start_station || '', '→', actions.selected.ticket.dest_station || '', actions.selected.ticket.depart_time || ''].join(' ') : ''}
            Caption {text:'1. 前往官網，輸入取票識別碼、訂位代碼與驗證碼。核對行程後選擇取消／修改訂位，完成官網最後確認。已付款訂位請先確認退票費用。'}
            RowLayout {
                AppButton {text:'複製訂位代碼'; onClicked:backend.copyCode(actions.selected.code)}
                AppButton {text:'前往官網取消'; primary:true; onClicked:backend.openCancellation(actions.selected.code)}
            }
            Caption {text:'2. 官網顯示取消成功後，回到此處確認。只開啟官網或關閉此視窗不會取消訂位，也不會移除本機紀錄。'}
            CheckBox {id:cancellationConfirmed; text:'我已在官網確認這筆訂位取消成功'}
            RowLayout {
                AppButton {text:'尚未完成，返回'; onClicked:cancellationDialog.close()}
                AppButton {text:'記錄已取消並封存'; enabled:cancellationConfirmed.checked && !backend.running
                    onClicked:{backend.confirmCancellation(actions.selected.code, actions.selected.fingerprint, cancellationConfirmed.checked); cancellationDialog.close()}}
            }
        }
    }
    Dialog {
        id:archiveDialog; title:'移至歷史'; anchors.centerIn:parent; modal:true; width:440
        standardButtons:Dialog.Ok | Dialog.Cancel
        Label {width:parent.width; wrapMode:Text.WordWrap; text:'訂位 ' + (actions.selected ? actions.selected.code : '') + ' 將從目前紀錄移出。官網訂位保留，完整紀錄仍可在歷史中查看。'}
        onAccepted:backend.archive(actions.selected.code)
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
                    onClicked:{backend.resolve(actions.selected.fingerprint, ['','booked','not_booked','cancelled'][outcome.currentIndex], confirmedCode.text, checkedWebsite.checked); resolveDialog.close()}
                }
            }
        }
    }
}
