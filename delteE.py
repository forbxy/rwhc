import numpy as np
from convert_utils import *
from meta_data import *

def deltaE2000(lab1, lab2, kL=1, kC=1, kH=1):
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    avg_C = (C1 + C2) / 2.0

    G = 0.5 * (1 - np.sqrt((avg_C**7) / (avg_C**7 + 25**7)))
    a1p = (1 + G) * a1
    a2p = (1 + G) * a2
    C1p = np.hypot(a1p, b1)
    C2p = np.hypot(a2p, b2)
    avg_Cp = (C1p + C2p) / 2.0

    h1p = (np.degrees(np.arctan2(b1, a1p)) % 360)
    h2p = (np.degrees(np.arctan2(b2, a2p)) % 360)

    dLp = L2 - L1
    dCp = C2p - C1p

    dhp = h2p - h1p
    if dhp > 180: dhp -= 360
    elif dhp < -180: dhp += 360
    if C1p * C2p == 0: dhp = 0.0

    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp) / 2)

    avg_Lp = (L1 + L2) / 2.0
    if abs(h1p - h2p) > 180:
        avg_hp = (h1p + h2p + 360) / 2.0
    else:
        avg_hp = (h1p + h2p) / 2.0
    if C1p * C2p == 0:
        avg_hp = h1p + h2p

    T = (1
         - 0.17 * np.cos(np.radians(avg_hp - 30))
         + 0.24 * np.cos(np.radians(2 * avg_hp))
         + 0.32 * np.cos(np.radians(3 * avg_hp + 6))
         - 0.20 * np.cos(np.radians(4 * avg_hp - 63)))

    d_ro = 30 * np.exp(-((avg_hp - 275) / 25)**2)
    RC = 2 * np.sqrt((avg_Cp**7) / (avg_Cp**7 + 25**7))
    SL = 1 + (0.015 * (avg_Lp - 50)**2) / np.sqrt(20 + (avg_Lp - 50)**2)
    SC = 1 + 0.045 * avg_Cp
    SH = 1 + 0.015 * avg_Cp * T
    RT = -np.sin(np.radians(2 * d_ro)) * RC

    return np.sqrt(
        (dLp / (kL * SL))**2 +
        (dCp / (kC * SC))**2 +
        (dHp / (kH * SH))**2 +
        RT * (dCp / (kC * SC)) * (dHp / (kH * SH))
    )

def XYZdeltaE2000(XYZ1, XYZ2):
    lab1 = XYZ_to_Lab_pqnorm(XYZ1, xyY_to_XYZ([*D65_WHITE_POINT, 1000]).tolist())
    lab2 = XYZ_to_Lab_pqnorm(XYZ2, xyY_to_XYZ([*D65_WHITE_POINT, 1000]).tolist())
    return deltaE2000(lab1, lab2)

def XYZdeltaE_ITP(XYZ1, XYZ2):

    XYZ1 = np.asarray(XYZ1, dtype=float)
    XYZ2 = np.asarray(XYZ2, dtype=float)
    ITP1 = XYZ_to_ictcp(XYZ1)
    ITP2 = XYZ_to_ictcp(XYZ2)
    dI = ITP2[..., 0] - ITP1[..., 0]
    dT = ITP2[..., 1] - ITP1[..., 1]
    dP = ITP2[..., 2] - ITP1[..., 2]
    

    delta_E = 720 * np.sqrt(dI**2 + 0.25 * (dT**2) + dP**2)
    return delta_E

if __name__ == "__main__":
    print(xyY_to_XYZ([*D65_WHITE_POINT, 10000]))
    p1 = np.array([1, 1, 1]) / 10000.0
    p2 = np.array([1.01, 1.01, 1.01]) / 10000.0

    print(XYZdeltaE2000(p1, p2))  
    print(XYZdeltaE_ITP(p1, p2))  
