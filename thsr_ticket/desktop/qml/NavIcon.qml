import QtQuick

Canvas {
    id: icon
    property int kind: 0
    property color ink: '#a7b7c5'
    implicitWidth: 20; implicitHeight: 20
    onInkChanged: requestPaint()
    onPaint: {
        let c = getContext('2d'); c.clearRect(0,0,width,height)
        c.strokeStyle = ink; c.lineWidth = 1.5; c.lineCap = 'round'; c.beginPath()
        if (kind === 0) {
            c.rect(2,2,6,6); c.rect(12,2,6,6); c.rect(2,12,6,6); c.rect(12,12,6,6)
        } else if (kind === 1) {
            c.moveTo(10,3); c.lineTo(10,17); c.moveTo(3,10); c.lineTo(17,10)
        } else if (kind === 2) {
            c.arc(10,10,8,0,2*Math.PI); c.moveTo(10,5); c.lineTo(10,10); c.lineTo(14,12)
        } else if (kind === 3) {
            c.rect(3,2,14,16); c.moveTo(6,7); c.lineTo(14,7); c.moveTo(6,12); c.lineTo(14,12)
        } else {
            for (let i=0;i<3;i++) {let y=4+i*6; c.moveTo(2,y);c.lineTo(18,y)}
            c.moveTo(6,2);c.lineTo(6,6);c.moveTo(14,8);c.lineTo(14,12);c.moveTo(8,14);c.lineTo(8,18)
        }
        c.stroke()
    }
}
