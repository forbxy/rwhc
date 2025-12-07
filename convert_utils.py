import numpy as np

# XYZ全部为PQ最大亮度10000nit归一化后数据，白点全部为D65白点


# 定义 PQ 常数（根据 SMPTE ST.2084）
m1 = 2610 / 16384
m2 = 2523 / 32
c1 = 3424 / 4096
c2 = 2413 / 128
c3 = 2392 / 128

EPSILON = 1e-10

def pq_eotf(V):
    """
    ST 2084 (PQ) EOTF: PQ code (0..1) -> Luminance L (cd/m², absolute)
    向量化实现，支持标量或 ndarray。
    """
    V = np.clip(np.asarray(V, dtype=np.float64), 0.0, 1.0)
    vp = np.power(V, 1.0 / m2)
    num = np.maximum(vp - c1, 0.0)
    den = np.maximum(c2 - c3 * vp, EPSILON)
    L_norm = np.clip(np.power(num / den, 1.0 / m1), 0.0, 1.0)
    return L_norm * 10000                    

def pq_oetf(L):
    """
    ST 2084 (PQ) 逆EOTF: Luminance L (cd/m², absolute) -> PQ code (0..1)
    向量化实现，支持标量或 ndarray。
    """
    L = np.clip(np.asarray(L/10000, dtype=np.float64), 0.0, 1.0)
    Lm = np.power(L, m1)             
    y = (c1 + c2 * Lm) / np.maximum(1.0 + c3 * Lm, EPSILON)
    V = np.power(np.clip(y, 0.0, None), m2)
    return np.clip(V, 0.0, 1.0)

def pq_encode(rgb_linear):
    # PQ OETF：Linear(0..1) -> PQ-coded(0..1)
    rgb_scaled = np.clip(np.asarray(rgb_linear), 0.0, 1.0)
    num = c1 + c2 * np.power(rgb_scaled, m1)
    denom = 1 + c3 * np.power(rgb_scaled, m1)
    return np.power(num / denom, m2)

def pq_decode(rgb_pq):
    # PQ EOTF：PQ-coded(0..1) -> Linear(0..1)
    E = np.clip(np.asarray(rgb_pq, dtype=float), 0.0, 1.0)
    # 避免负数进入后续开方
    E_pow = np.power(E, 1.0 / m2)
    num = np.maximum(E_pow - c1, 0.0)
    denom = c2 - c3 * E_pow
    # 防止除零
    denom = np.where(denom <= 0, np.nan, denom)
    R = num / denom
    linear = np.clip(np.power(np.clip(R, 0.0, None), 1.0 / m1), 0.0, 1.0)
    return linear

def pq_encode_with_lut(rgb_linear, lut):
    # rgb_linear: 0..1
    # lut: windows mhc2 lut {"red_lut":[], "green_lut":[], "blue_lut":[]}
    pq = pq_encode(rgb_linear)
    
    lut_fixed = apply_lut(pq, lut)
    return lut_fixed

def pq_decode_with_reversed_lut(rgb_pq, inversed_lut):
    """
    rgb_pq: 0..1
    reverse_lut: windows mhc2 lut reversed_lut {"red_lut":[], 
                                                 "green_lut":[],
                                                 "blue_lut":[]}
    """
    if not (isinstance(inversed_lut, (list, tuple)) and len(inversed_lut) == 3):
        raise ValueError("reverse_lut must be a sequence of three 1D arrays for R,G,B")

    lut_fixed = apply_lut(rgb_pq, inversed_lut)
    linear = pq_decode(lut_fixed)
    return linear

def srgb_encode(code):
    """
    sRGB 逆OETF：sRGB code(0..1) -> Linear(0..1)
    向量化实现，支持标量或 ndarray。
    """
    v = np.clip(np.asarray(code, dtype=np.float64), 0.0, 1.0)
    a = 0.055
    thresh = 0.04045
    return np.where(v <= thresh, v / 12.92, np.power((v + a) / (1 + a), 2.4))

def srgb_decode(lin):
    """
    sRGB OETF：Linear(0..1) -> sRGB code(0..1)
    向量化实现，支持标量或 ndarray。
    """
    x = np.clip(np.asarray(lin, dtype=np.float64), 0.0, 1.0)
    a = 0.055
    thresh = 0.0031308
    return np.where(x <= thresh, x * 12.92, (1 + a) * np.power(x, 1/2.4) - a)

def gamma_encode(code, gamma: float):
    """
    Gamma 逆OETF：Gamma-coded -> Linear，lin = code^gamma
    向量化实现，支持标量或 ndarray。
    """
    code = np.clip(np.asarray(code, dtype=np.float64), 0.0, 1.0)
    g = max(float(gamma), 1e-6)
    return np.power(code, g)

def gamma_decode(lin, gamma: float):
    """
    Gamma OETF：Linear -> Gamma-coded，code = lin^(1/gamma)
    向量化实现，支持标量或 ndarray。
    """
    lin = np.clip(np.asarray(lin, dtype=np.float64), 0.0, 1.0)
    g = max(float(gamma), 1e-6)
    return np.power(lin, 1.0 / g)

def apply_lut(rgb, lut):
    lR = np.asarray(lut["red_lut"], dtype=float).ravel()
    lG = np.asarray(lut["green_lut"], dtype=float).ravel()
    lB = np.asarray(lut["blue_lut"], dtype=float).ravel()
    M = len(lR)
    if M < 2 or len(lG) != M or len(lB) != M:
        raise ValueError("all LUT channels must have the same length >= 2")

    scale = M - 1
    idx = np.clip(np.rint(rgb * scale).astype(np.int32), 0, scale)

    # 按通道查表
    lut_applied = np.empty_like(rgb, dtype=float)
    lut_applied[..., 0] = lR[idx[..., 0]]
    lut_applied[..., 1] = lG[idx[..., 1]]
    lut_applied[..., 2] = lB[idx[..., 2]]
    return lut_applied

def f(t):
    delta = 6/29
    return np.where(t > delta**3, t**(1/3), (t * (1/(3 * delta**2))) + (4/29))

def f_inv(t):
    delta = 6/29
    return np.where(t > delta, t**3, 3 * delta**2 * (t - 4/29))

def XYZ_to_Lab(XYZ, whitepoint):
    XYZ = np.array(XYZ)
    whitepoint = np.array(whitepoint)
    X, Y, Z = XYZ / whitepoint  # Normalize by whitepoint
    fx, fy, fz = f(X), f(Y), f(Z)

    L = 116 * fy - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)
    return np.array([L, a, b])

def Lab_to_XYZ(Lab, whitepoint):
    L, a, b = Lab
    fy = (L + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200

    X = whitepoint[0] * f_inv(fx)
    Y = whitepoint[1] * f_inv(fy)
    Z = whitepoint[2] * f_inv(fz)
    return np.array([X, Y, Z])

def desaturate_XYZ(XYZ, whitepoint, saturation=0.5):
    """
    实现 XYZ → Lab → 降饱和度 → XYZ。
    saturation: 0 = 去饱和成灰，1 = 保持原色，0.5 = 一半饱和度
    """
    XYZ = np.array(XYZ)
    whitepoint = np.array(whitepoint)
    Lab = XYZ_to_Lab(XYZ, whitepoint)
    Lab[1] *= saturation  # a*
    Lab[2] *= saturation  # b*
    return Lab_to_XYZ(Lab, whitepoint)


def XYZ_to_xy(XYZ):
    """
    支持批量的 XYZ -> xy
    输入:
        XYZ: 形状 (...,3) 或 (3,) 的数组/列表
    返回:
        形状 (...,2) 的数组，每个元素为 (x,y)
        若 X+Y+Z=0，则对应位置返回 (nan,nan)
    """
    arr = np.asarray(XYZ, dtype=float)
    # 若是 (3,) 或 (3,N) 老式输入，统一转为 (...,3)
    if arr.ndim == 1:
        if arr.shape[0] != 3:
            raise ValueError("XYZ length must be 3")
        arr = arr.reshape(1, 3)
        squeeze_back = True
    else:
        if arr.shape[-1] != 3:
            raise ValueError("Last dim of XYZ must be 3")
        squeeze_back = False

    denom = arr[..., 0] + arr[..., 1] + arr[..., 2]
    denom_safe = np.where(denom == 0, np.nan, denom)
    x = arr[..., 0] / denom_safe
    y = arr[..., 1] / denom_safe
    xy = np.stack([x, y], axis=-1)
    if squeeze_back:
        return xy[0]
    return xy

def XYZ_to_xyY(XYZ):
    arr = np.asarray(XYZ, dtype=float)
    # 若是 (3,) 或 (3,N) 老式输入，统一转为 (...,3)
    if arr.ndim == 1:
        if arr.shape[0] != 3:
            raise ValueError("XYZ length must be 3")
        arr = arr.reshape(1, 3)
        squeeze_back = True
    else:
        if arr.shape[-1] != 3:
            raise ValueError("Last dim of XYZ must be 3")
        squeeze_back = False

    denom = arr[..., 0] + arr[..., 1] + arr[..., 2]
    denom_safe = np.where(denom == 0, np.nan, denom)
    x = arr[..., 0] / denom_safe
    y = arr[..., 1] / denom_safe
    Y = arr[..., 1]
    xyY = np.stack([x, y, Y], axis=-1)
    if squeeze_back:
        return xyY[0]
    return xyY

def xyY_to_XYZ(xyY):
    """
    xyY -> XYZ 转换，支持批量。
    输入:
        xyY: 形状 (3,) 或 (...,3)，顺序 (x, y, Y)。
             其中 Y 为绝对亮度 (nits)，函数内部除以 10000
             (项目全局约定：XYZ 已按 10000 nits 归一化，1 = 10000 nits)。
    返回:
        XYZ: 形状与输入对应，最后一维为 3，单位为归一化绝对亮度 (1=10000 nits)。
    规则:
        y<=0 或 x<0 或 y<0 或 x+y>1 视为非法，输出对应位置 [0,0,0]。
    """
    arr = np.asarray(xyY, dtype=float)
    if arr.shape[-1] != 3:
        raise ValueError("xyY last dimension must be 3 (x,y,Y)")
    squeeze = (arr.ndim == 1)
    if squeeze:
        arr = arr.reshape(1, 3)

    x = arr[:, 0]
    y = arr[:, 1]
    Y_abs = arr[:, 2]  # nits
    Y_norm = Y_abs / 10000.0

    valid = (y > 0) & (x >= 0) & (y >= 0) & (x + y <= 1 + 1e-12)
    safe_y = np.where(valid, y, 1.0)

    X = (x / safe_y) * Y_norm
    Z = ((1.0 - x - y) / safe_y) * Y_norm

    X = np.where(valid, X, 0.0)
    Y_out = np.where(valid, Y_norm, 0.0)
    Z = np.where(valid, Z, 0.0)
    Z = np.where(np.abs(Z) < EPSILON, 0.0, Z)

    out = np.stack([X, Y_out, Z], axis=-1)
    if squeeze:
        return out[0]
    return out

def l2_normalize_XYZ(xyz, eps: float = 1e-12):
    """
    L2 normalization of XYZ (or任意 3D 向量).
    输入:
        xyz: array-like (...,3)
        eps: 防止除零的最小范数
    返回:
        与 xyz 同形状的单位向量 (||v||=1 或原本为零向量则保持零)
    """
    v = np.asarray(xyz, dtype=float)
    norm = np.linalg.norm(v, axis=-1, keepdims=True)
    norm_safe = np.maximum(norm, eps)
    out = v / norm_safe
    # 对原本范数 < eps 的向量，保持为0
    out = np.where(norm < eps, 0.0, out)
    return out

def XYZ_to_bt2020_linear(xyz):
    # XYZ → 线性 BT.2020 RGB 矩阵
    XYZ_to_BT2020 = np.array([
        [ 1.71665119, -0.35567078, -0.25336628],
        [-0.66668435,  1.61648124,  0.01576855],
        [ 0.01763986, -0.04277061,  0.94210312]
    ])
    rgb_linear = np.dot(XYZ_to_BT2020, xyz)
    # 裁剪负值（防止 PQ 输入非法）
    rgb_linear = np.clip(rgb_linear, 0, None)
    return rgb_linear

def BT2020_linear_to_XYZ(rgb_linear):
    """
    线性 BT.2020 RGB → XYZ
    输入:
        rgb_linear: 长度为3的一维数组/列表，或形状(3,)的 numpy 数组
    返回:
        xyz: 形状(3,) 的 XYZ，相同的 0~1 归一化相对亮度空间
    说明:
        使用与 xyz_to_bt2020_linear 中矩阵互逆的标准 BT.2020 正向矩阵。
    """
    BT2020_to_XYZ = np.array([
        [0.6369580483012914, 0.14461690358620832, 0.16888097516417210],
        [0.2627002120112671, 0.67799807151887080, 0.05930171646986196],
        [0.0000000000000000, 0.02807269304908743, 1.06098505771079100]
    ])
    rgb_linear = np.asarray(rgb_linear, dtype=float)
    xyz = np.dot(BT2020_to_XYZ, rgb_linear)
    xyz = np.where(xyz < 0, 0.0, xyz)
    return xyz

def XYZ_to_BT2020_PQ_rgb(xyz):
    """
    将相对归一化的 CIEXYZ 转换为 PQ 编码的 BT.2020 RGB。
    假设 xyz 范围已归一化至 [0,1]，无需考虑绝对亮度单位。
    """
    rgb_linear = XYZ_to_bt2020_linear(xyz)
    rgb_pq = pq_encode(rgb_linear)
    return rgb_pq

def BT2020_PQ_rgb_to_XYZ(rgb_pq):
    """
    将 PQ 编码的 BT.2020 RGB 转换为相对归一化的 CIEXYZ。
    假设 rgb_pq 范围已归一化至 [0,1]，无需考虑绝对亮度单位。
    """
    rgb_linear = pq_decode(rgb_pq)
    xyz = BT2020_linear_to_XYZ(rgb_linear)
    return xyz

def XYZ_to_Lab_pqnorm(xyz_norm, white_point_norm):
    """
    将 PQ 归一化(÷10000)后的 XYZ 转换为 Lab。
    - xyz_norm: 已经 /10000 的 XYZ
    - white_point_norm: 已经 /10000 的参考白点XYZ（若提供，则忽略 white_luminance_nits）
    """
    xyz_norm = np.array(xyz_norm, dtype=float)
    white_point_norm = np.array(white_point_norm, dtype=float)

    # 归一到参考白
    t = xyz_norm / white_point_norm

    # Lab 非线性
    delta = 6/29
    def f(v):
        return np.where(v > delta**3, np.cbrt(v), (v/(3*delta**2)) + 4/29)

    fx, fy, fz = f(t[0]), f(t[1]), f(t[2])
    L = 116 * fy - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)
    return np.array([L, a, b])

def xy_primaries_to_XYZ_normed(primaries: dict, Yn=1.0):
    """
    将色域定义中的RGBW(x,y)转换为按白点归一化的 XYZ（使白点的 Y=Yn）。
    输入:
      primaries: {
        "red": (xr, yr),
        "green": (xg, yg),
        "blue": (xb, yb),
        "white": (xw, yw)
      }
      Yn: 归一化白点的亮度（0-1）
    返回:
      {
        "rXYZ": [X,Y,Z],
        "gXYZ": [X,Y,Z],
        "bXYZ": [X,Y,Z],
        "wtpt": [X,Y,Z]   # 白点 XYZ，Y=Yn
      }
    说明:
      先构造未缩放原色列向量 Rn,Gn,Bn（各自 Y=1 的 XYZ 方向），
      再求解缩放系数 S 使得 R*S_r + G*S_g + B*S_b = W（白点方向，Y=1），
      最后整体按 Yn 缩放，使白点 Y=Yn。
    """
    try:
        xr, yr = primaries["red"]
        xg, yg = primaries["green"]
        xb, yb = primaries["blue"]
        xw, yw = primaries["white"]
    except Exception:
        raise ValueError("primaries 需包含 red/green/blue/white 的 (x,y)")

    Rn = xyY_to_XYZ([xr, yr, Yn*10000])
    Gn = xyY_to_XYZ([xg, yg, Yn*10000])
    Bn = xyY_to_XYZ([xb, yb, Yn*10000])
    Wn = xyY_to_XYZ([xw, yw, Yn*10000])

    M = np.stack([Rn, Gn, Bn], axis=1)  # 3x3
    try:
        S = np.linalg.solve(M, Wn)  # 3x1
    except np.linalg.LinAlgError:
        raise ValueError("原色矩阵不可逆，无法从 xy 求归一化 XYZ")

    R = Rn * S[0]
    G = Gn * S[1]
    B = Bn * S[2]

    scale = float(Yn)
    R *= scale
    G *= scale
    B *= scale
    W = Wn * scale

    return {
        "red": R.tolist(),
        "green": G.tolist(),
        "blue": B.tolist(),
        "white": W.tolist()
    }

def rgb2020_linear_to_lms(rgb_linear):

    rgb_linear = np.asarray(rgb_linear, dtype=float)
    M = (np.array([
        [1688, 2146,  262],
        [ 683, 2951,  462],
        [  99,  309, 3688],
    ], dtype=float) / 4096.0)
    lms = np.dot(M, rgb_linear)
    # 在 PQ 前仅去负值
    return np.maximum(lms, 0.0)

def lms_p_to_ictcp(lmsp):

    lmsp = np.asarray(lmsp, dtype=float)
    M = (np.array([
        [ 2048,   2048,     0],
        [ 6610, -13613,  7003],
        [17933, -17390,   -543],
    ], dtype=float) / 4096.0)
    return np.dot(M, lmsp)

def XYZ_to_ictcp(xyz_norm):

    xyz_norm = np.asarray(xyz_norm, dtype=float)
    rgb2020 = XYZ_to_bt2020_linear(xyz_norm)
    lms = rgb2020_linear_to_lms(rgb2020)
    lmsp = pq_encode(np.clip(lms, 0.0, 1.0))
    return lms_p_to_ictcp(lmsp)

if __name__ == "__main__":
    from meta_data import D65_WHITE_POINT
    a = BT2020_PQ_rgb_to_XYZ([0.5, 0.5, 0.5])