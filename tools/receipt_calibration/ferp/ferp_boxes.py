import numpy as np, cv2, json
norm = cv2.imread('norm.png', cv2.IMREAD_GRAYSCALE)
R = {
 'logo': (150,0,420,192), 'title': (60,195,485,270), 'paid': (200,300,380,365), 'vat_label': (55,385,200,425),
 'vat': (290,390,595,428), 'address': (140,448,455,495), 'simplified': (150,503,445,558),
 'l_invno': (440,645,598,678), 'l_type': (440,695,598,728), 'l_pay': (440,745,598,776), 'l_serial': (440,776,598,815),
 'l_date': (440,815,598,848), 'l_close': (440,850,598,888), 'l_note': (440,903,598,938), 'l_cust': (440,952,598,990),
 'l_phone': (440,1005,598,1040),
 'v_invno': (150,645,300,680), 'v_type': (150,698,300,733), 'v_pay': (150,748,300,775), 'v_serial': (150,778,300,810),
 'v_date': (60,820,370,858), 'v_close': (60,860,370,898), 'v_note': (280,905,370,942), 'v_cust': (150,952,360,990),
 'v_phone': (150,1005,360,1042),
 'l_net': (440,1420,598,1455), 'v_net': (180,1418,300,1452), 'l_disc': (440,1468,598,1500), 'v_disc': (180,1465,300,1500),
 'l_vat': (370,1522,598,1560), 'v_vat': (180,1522,300,1558), 'l_total': (440,1590,598,1640), 'v_total': (170,1585,300,1630),
 'l_cashier': (480,1670,598,1708), 'v_cashier': (130,1648,250,1680), 'v_printed': (30,1678,345,1722),
 'phone': (115,1738,460,1795), 'qr': (160,1850,430,2110),
}
out = {}
for k, (x0,y0,x1,y1) in R.items():
    sub = norm[y0:y1, x0:x1] < 140
    # drop specks: require column/row to have >=1 px and remove isolated pixels via opening
    sub = cv2.morphologyEx(sub.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2,2),np.uint8)).astype(bool)
    ys, xs = np.nonzero(sub)
    out[k] = [int(x0+xs.min()), int(x0+xs.max()), int(y0+ys.min()), int(y0+ys.max())]
    print(f"{k:11s} x {out[k][0]:4d}-{out[k][1]:4d}  y {out[k][2]:4d}-{out[k][3]:4d}  w {out[k][1]-out[k][0]:3d} h {out[k][3]-out[k][2]:3d}  cx {(out[k][0]+out[k][1])/2:.0f}")
json.dump(out, open('ferp_boxes.json','w'))
