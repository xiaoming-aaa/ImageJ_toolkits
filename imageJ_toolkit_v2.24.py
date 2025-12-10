# @Context context

from ij import IJ, WindowManager, ImagePlus, Prefs
from ij.gui import GenericDialog, WaitForUserDialog, NewImage
from ij.plugin import Duplicator, ImageCalculator
from ij.measure import Measurements
from javax.swing import JFrame, JButton, JPanel, BoxLayout, BorderFactory, JSeparator, JLabel, Box, SwingConstants
from java.awt import Component, Dimension, Font, Color, BasicStroke, BorderLayout, Insets
from java.awt.dnd import DropTarget, DnDConstants, DropTargetAdapter
from java.awt.datatransfer import DataFlavor
from java.awt.event import WindowAdapter, ActionListener
from java.io import File
import threading
import time
import re
import os
import shutil

"""
Cell Image Analysis Toolbox v2.24 (GUI Version)
Author: Gemini
Language: Python (Jython) wrapper for Native ImageJ Macros

Description:
A persistent floating toolbox for high-quality cell image processing.
Now features customizable settings for modules.

Modules:
1. Apply ROI & Crop (Settings: Confirm Prompt, Apply to All)
2. Batch Merge Channels (Settings: Select Channels "1,2", Confirm Prompt)
3. Ratio Analysis (Settings: Full Calibration Bar parameters like Zoom, Decimals, Colors)
4. Scale Bar & Copy Sequence (Settings: Full Scale Bar parameters including Background)
5. Batch Brightness Control
6. Smart Undo (Settings: Max Steps, Confirm Prompt)
7. Close All

Updates (v2.24):
- **Module 3 Settings**: Fully matched the "Calibration Bar" native dialog.
    - Added: Fill/Label Colors, Number of Labels, Decimals, Zoom Factor, Show Unit.
- **Module 4 Settings**: Added "Background" color option to match native Scale Bar dialog.
"""

# ==========================================
# Global Variables & Constants
# ==========================================
LAST_DROPPED_FILES = []
CHECKPOINT_ROOT = os.path.join(IJ.getDirectory("temp"), "xiaoming_toolbox_checkpoints")
CHECKPOINT_STACK = []

# --- Prefs Keys ---

# Undo
PREF_UNDO_MAX_STEPS = "xiaoming.undo.max_steps"
PREF_UNDO_CONFIRM = "xiaoming.undo.confirm"

# Module 4: Scale Bar
PREF_SB_ENABLE_BAR = "xiaoming.sb.enable_bar"
PREF_SB_ENABLE_COPY = "xiaoming.sb.enable_copy"
PREF_SB_WIDTH = "xiaoming.sb.width"
PREF_SB_HEIGHT = "xiaoming.sb.height"
PREF_SB_FONT = "xiaoming.sb.font"
PREF_SB_COLOR = "xiaoming.sb.color"
PREF_SB_BG = "xiaoming.sb.bg" # New
PREF_SB_LOC = "xiaoming.sb.loc"
PREF_SB_BOLD = "xiaoming.sb.bold"
PREF_SB_HIDE = "xiaoming.sb.hide"
PREF_SB_OVERLAY = "xiaoming.sb.overlay"

# Module 1: ROI
PREF_ROI_CONFIRM = "xiaoming.roi.confirm"
PREF_ROI_APPLY_ALL = "xiaoming.roi.all"

# Module 2: Merge
PREF_MERGE_CHANNELS = "xiaoming.merge.channels"
PREF_MERGE_CONFIRM = "xiaoming.merge.confirm"

# Module 3: Ratio
PREF_RATIO_NUM = "xiaoming.ratio.num"
PREF_RATIO_DEN = "xiaoming.ratio.den"
PREF_RATIO_MIN = "xiaoming.ratio.min"
PREF_RATIO_MAX = "xiaoming.ratio.max"
PREF_RATIO_CONFIRM = "xiaoming.ratio.confirm"
PREF_RATIO_ADD_BAR = "xiaoming.ratio.add_bar"
# Calibration Bar Specifics
PREF_CB_LOC = "xiaoming.cb.loc"
PREF_CB_FILL = "xiaoming.cb.fill"
PREF_CB_LABEL = "xiaoming.cb.label"
PREF_CB_NUM = "xiaoming.cb.num"
PREF_CB_DEC = "xiaoming.cb.dec"
PREF_CB_FONT = "xiaoming.cb.font"
PREF_CB_ZOOM = "xiaoming.cb.zoom"
PREF_CB_BOLD = "xiaoming.cb.bold"
PREF_CB_OVERLAY = "xiaoming.cb.overlay"
PREF_CB_UNIT = "xiaoming.cb.unit"

# ==========================================
# Settings Logic
# ==========================================

# --- ROI Settings ---
def get_roi_prefs():
    confirm = str(Prefs.get(PREF_ROI_CONFIRM, "true")).lower() == "true"
    apply_all = str(Prefs.get(PREF_ROI_APPLY_ALL, "true")).lower() == "true"
    return {"confirm": confirm, "apply_all": apply_all}

def show_roi_settings():
    try:
        p = get_roi_prefs()
        gd = GenericDialog("Settings: ROI & Crop")
        gd.addCheckbox(u"\u6267\u884c\u524d\u63d0\u793a (Confirm before crop)", p["confirm"])
        gd.addCheckbox(u"\u5e94\u7528\u5230\u6240\u6709\u56fe\u7247 (Apply to all images)", p["apply_all"])
        gd.showDialog()
        if gd.wasCanceled(): return
        Prefs.set(PREF_ROI_CONFIRM, str(gd.getNextBoolean()).lower())
        Prefs.set(PREF_ROI_APPLY_ALL, str(gd.getNextBoolean()).lower())
        Prefs.savePreferences()
        IJ.showStatus("ROI Settings saved.")
    except Exception as e: IJ.log("Error settings: " + str(e))

# --- Merge Settings ---
def get_merge_prefs():
    channels = Prefs.get(PREF_MERGE_CHANNELS, "1,2,3,4")
    confirm = str(Prefs.get(PREF_MERGE_CONFIRM, "true")).lower() == "true"
    return {"channels": channels, "confirm": confirm}

def show_merge_settings():
    try:
        p = get_merge_prefs()
        gd = GenericDialog("Settings: Batch Merge")
        gd.addMessage(u"输入要融合的通道编号 (用逗号分隔):")
        gd.addStringField(u"通道 (Channels):", p["channels"], 10)
        gd.addCheckbox(u"\u6267\u884c\u524d\u63d0\u793a (Confirm before running)", p["confirm"])
        gd.showDialog()
        if gd.wasCanceled(): return
        new_chs = gd.getNextString()
        if not re.match(r'^[\d, ]+$', new_chs): return
        Prefs.set(PREF_MERGE_CHANNELS, new_chs)
        Prefs.set(PREF_MERGE_CONFIRM, str(gd.getNextBoolean()).lower())
        Prefs.savePreferences()
        IJ.showStatus("Merge Settings saved.")
    except Exception as e: IJ.log("Error settings: " + str(e))

# --- Ratio Settings (Calibration Bar) ---
def get_ratio_prefs():
    return {
        "num": int(Prefs.get(PREF_RATIO_NUM, 1)),
        "den": int(Prefs.get(PREF_RATIO_DEN, 2)),
        "min": float(Prefs.get(PREF_RATIO_MIN, 0.0)),
        "max": float(Prefs.get(PREF_RATIO_MAX, 2.0)),
        "confirm": str(Prefs.get(PREF_RATIO_CONFIRM, "true")).lower() == "true",
        "add_bar": str(Prefs.get(PREF_RATIO_ADD_BAR, "true")).lower() == "true",
        # Calibration Bar Params
        "loc": Prefs.get(PREF_CB_LOC, "Upper Right"),
        "fill": Prefs.get(PREF_CB_FILL, "White"),
        "label": Prefs.get(PREF_CB_LABEL, "Black"),
        "n_labels": int(Prefs.get(PREF_CB_NUM, 5)),
        "dec": int(Prefs.get(PREF_CB_DEC, 2)),
        "font": int(Prefs.get(PREF_CB_FONT, 12)),
        "zoom": float(Prefs.get(PREF_CB_ZOOM, 1.0)),
        "bold": str(Prefs.get(PREF_CB_BOLD, "false")).lower() == "true",
        "overlay": str(Prefs.get(PREF_CB_OVERLAY, "true")).lower() == "true",
        "unit": str(Prefs.get(PREF_CB_UNIT, "false")).lower() == "true"
    }

def show_ratio_settings():
    try:
        p = get_ratio_prefs()
        locs = ["Upper Right", "Lower Right", "Upper Left", "Lower Left", "At Selection"]
        colors = ["White", "Black", "Light Gray", "Gray", "Dark Gray", "Red", "Green", "Blue", "Yellow", "None"]
        
        gd = GenericDialog("Settings: Ratio Analysis")
        gd.addMessage("--- Calculation ---")
        gd.addNumericField("Numerator Ch:", p["num"], 0)
        gd.addNumericField("Denominator Ch:", p["den"], 0)
        gd.addNumericField("Default Min:", p["min"], 2)
        gd.addNumericField("Default Max:", p["max"], 2)
        gd.addCheckbox("Confirm before running", p["confirm"])
        
        gd.addMessage("--- Calibration Bar (Native Options) ---")
        gd.addCheckbox("Add Calibration Bar", p["add_bar"])
        
        gd.addChoice("Location:", locs, p["loc"])
        gd.addChoice("Fill color:", colors, p["fill"])
        gd.addChoice("Label color:", colors, p["label"])
        gd.addNumericField("Number of labels:", p["n_labels"], 0)
        gd.addNumericField("Decimal places:", p["dec"], 0)
        gd.addNumericField("Font size:", p["font"], 0)
        gd.addNumericField("Zoom factor:", p["zoom"], 1)
        
        gd.setInsets(0, 20, 0); gd.addCheckbox("Bold text", p["bold"])
        gd.setInsets(0, 20, 0); gd.addCheckbox("Overlay", p["overlay"])
        gd.setInsets(0, 20, 0); gd.addCheckbox("Show unit", p["unit"])
        
        gd.showDialog()
        if gd.wasCanceled(): return
        
        Prefs.set(PREF_RATIO_NUM, int(gd.getNextNumber()))
        Prefs.set(PREF_RATIO_DEN, int(gd.getNextNumber()))
        Prefs.set(PREF_RATIO_MIN, float(gd.getNextNumber()))
        Prefs.set(PREF_RATIO_MAX, float(gd.getNextNumber()))
        Prefs.set(PREF_RATIO_CONFIRM, str(gd.getNextBoolean()).lower())
        Prefs.set(PREF_RATIO_ADD_BAR, str(gd.getNextBoolean()).lower())
        
        Prefs.set(PREF_CB_LOC, gd.getNextChoice())
        Prefs.set(PREF_CB_FILL, gd.getNextChoice())
        Prefs.set(PREF_CB_LABEL, gd.getNextChoice())
        Prefs.set(PREF_CB_NUM, int(gd.getNextNumber()))
        Prefs.set(PREF_CB_DEC, int(gd.getNextNumber()))
        Prefs.set(PREF_CB_FONT, int(gd.getNextNumber()))
        Prefs.set(PREF_CB_ZOOM, float(gd.getNextNumber()))
        
        Prefs.set(PREF_CB_BOLD, str(gd.getNextBoolean()).lower())
        Prefs.set(PREF_CB_OVERLAY, str(gd.getNextBoolean()).lower())
        Prefs.set(PREF_CB_UNIT, str(gd.getNextBoolean()).lower())
        
        Prefs.savePreferences()
        IJ.showStatus("Ratio Settings saved.")
    except Exception as e: IJ.log("Error settings: " + str(e))

# --- Undo Settings ---
def get_undo_max_steps():
    val = Prefs.get(PREF_UNDO_MAX_STEPS, 5.0)
    return int(max(1, min(10, val)))

def get_undo_confirm():
    val = Prefs.get(PREF_UNDO_CONFIRM, "true")
    if val is None: return True
    return str(val).lower() == "true"

def show_undo_settings():
    try:
        current_steps = float(get_undo_max_steps()) 
        current_confirm = bool(get_undo_confirm())
        gd = GenericDialog("Settings: Smart Undo")
        gd.addSlider(u"\u6700\u5927\u64a4\u56de\u6b65\u6570 (Max Steps):", 1.0, 10.0, current_steps)
        gd.addCheckbox(u"\u6267\u884c\u524d\u63d0\u793a (Confirm before running)", current_confirm)
        gd.showDialog()
        if gd.wasCanceled(): return
        new_steps = int(gd.getNextNumber())
        new_confirm = gd.getNextBoolean()
        Prefs.set(PREF_UNDO_MAX_STEPS, float(new_steps))
        Prefs.set(PREF_UNDO_CONFIRM, str(new_confirm).lower())
        Prefs.savePreferences()
        IJ.showStatus("Undo Settings saved.")
    except Exception as e: IJ.log("Error settings: " + str(e))

# --- Scale Bar Settings (Module 4) ---
def get_sb_prefs():
    return {
        "enable_bar": str(Prefs.get(PREF_SB_ENABLE_BAR, "true")).lower() == "true",
        "enable_copy": str(Prefs.get(PREF_SB_ENABLE_COPY, "true")).lower() == "true",
        "width": float(Prefs.get(PREF_SB_WIDTH, 10.0)),
        "height": int(Prefs.get(PREF_SB_HEIGHT, 8.0)),
        "font": int(Prefs.get(PREF_SB_FONT, 14.0)),
        "color": Prefs.get(PREF_SB_COLOR, "White"),
        "bg": Prefs.get(PREF_SB_BG, "None"), # Added Background
        "location": Prefs.get(PREF_SB_LOC, "Lower Right"),
        "bold": str(Prefs.get(PREF_SB_BOLD, "true")).lower() == "true",
        "hide": str(Prefs.get(PREF_SB_HIDE, "true")).lower() == "true",
        "overlay": str(Prefs.get(PREF_SB_OVERLAY, "true")).lower() == "true"
    }

def show_scalebar_settings():
    try:
        p = get_sb_prefs()
        colors = ["White", "Black", "Light Gray", "Gray", "Dark Gray", "Red", "Green", "Blue", "Yellow", "None"]
        locs = ["Lower Right", "Lower Left", "Upper Right", "Upper Left", "At Selection"]
        
        gd = GenericDialog("Settings: Scale Bar & Copy")
        gd.addMessage("--- Actions ---")
        gd.addCheckbox(u"\u6267\u884c: \u6dfb\u52a0\u6bd4\u4f8b\u5c3a (Add Scale Bar)", p["enable_bar"])
        gd.addCheckbox(u"\u6267\u884c: \u590d\u5236\u5230\u526a\u8d34\u677f (Copy Sequence)", p["enable_copy"])
        gd.addMessage("--- Scale Bar Parameters ---")
        gd.addNumericField("Width in units:", p["width"], 1)
        gd.addNumericField("Height in pixels:", p["height"], 0)
        gd.addNumericField("Font size:", p["font"], 0)
        gd.addChoice("Color:", colors, p["color"])
        gd.addChoice("Background:", colors, p["bg"]) # Added
        gd.addChoice("Location:", locs, p["location"])
        gd.setInsets(0, 20, 0); gd.addCheckbox("Bold text", p["bold"])
        gd.setInsets(0, 20, 0); gd.addCheckbox("Hide text", p["hide"])
        gd.setInsets(0, 20, 0); gd.addCheckbox("Overlay", p["overlay"])
        
        gd.showDialog()
        if gd.wasCanceled(): return
        
        Prefs.set(PREF_SB_ENABLE_BAR, str(gd.getNextBoolean()).lower())
        Prefs.set(PREF_SB_ENABLE_COPY, str(gd.getNextBoolean()).lower())
        Prefs.set(PREF_SB_WIDTH, float(gd.getNextNumber()))
        Prefs.set(PREF_SB_HEIGHT, float(gd.getNextNumber())) 
        Prefs.set(PREF_SB_FONT, float(gd.getNextNumber()))
        Prefs.set(PREF_SB_COLOR, gd.getNextChoice())
        Prefs.set(PREF_SB_BG, gd.getNextChoice()) # Save
        Prefs.set(PREF_SB_LOC, gd.getNextChoice())
        Prefs.set(PREF_SB_BOLD, str(gd.getNextBoolean()).lower())
        Prefs.set(PREF_SB_HIDE, str(gd.getNextBoolean()).lower())
        Prefs.set(PREF_SB_OVERLAY, str(gd.getNextBoolean()).lower())
        Prefs.savePreferences()
        IJ.showStatus("Scale Bar Settings saved.")
    except Exception as e: IJ.log("Error settings: " + str(e))

def show_settings_placeholder(module_name):
    IJ.showMessage("Settings: " + module_name, u"\u8be5\u6a21\u5757\u6682\u65e0\u53ef\u914d\u7f6e\u7684\u9ed8\u8ba4\u53c2\u6570\u3002\n(No settings available yet)")

# ==========================================
# Checkpoint Logic
# ==========================================

def ensure_checkpoint_root():
    d = File(CHECKPOINT_ROOT)
    if not d.exists():
        d.mkdirs()
    return d

def cleanup_all_checkpoints():
    global CHECKPOINT_STACK
    d = File(CHECKPOINT_ROOT)
    if d.exists():
        try:
            shutil.rmtree(CHECKPOINT_ROOT)
        except:
            pass 
    CHECKPOINT_STACK = []

def save_checkpoint():
    global CHECKPOINT_STACK
    ids = WindowManager.getIDList()
    if not ids: return 
    ensure_checkpoint_root()
    timestamp = str(int(time.time() * 1000))
    chk_folder = os.path.join(CHECKPOINT_ROOT, "chk_" + timestamp)
    os.mkdir(chk_folder)
    for id in ids:
        imp = WindowManager.getImage(id)
        if imp:
            safe_title = imp.getTitle().replace("/", "_").replace("\\", "_")
            save_path = os.path.join(chk_folder, safe_title)
            if not save_path.lower().endswith(".tif"):
                save_path += ".tif"
            IJ.saveAs(imp, "Tiff", save_path)
            imp.setTitle(safe_title.replace(".tif", "")) 
    CHECKPOINT_STACK.append(chk_folder)
    max_steps = get_undo_max_steps()
    while len(CHECKPOINT_STACK) > max_steps:
        oldest_folder = CHECKPOINT_STACK.pop(0)
        try: shutil.rmtree(oldest_folder)
        except: pass

def restore_last_checkpoint():
    global CHECKPOINT_STACK
    if not CHECKPOINT_STACK: return False
    last_folder_path = CHECKPOINT_STACK.pop()
    last_folder = File(last_folder_path)
    if not last_folder.exists(): return False
    ids = WindowManager.getIDList()
    if ids:
        for id in ids:
            imp = WindowManager.getImage(id)
            if imp: imp.changes = False; imp.close()
    files = last_folder.listFiles()
    if files:
        for f in files:
            if f.getName().lower().endswith(".tif"):
                imp = IJ.openImage(f.getAbsolutePath())
                if imp:
                    orig_name = f.getName()[:-4]
                    imp.setTitle(orig_name)
                    imp.show()
    try: shutil.rmtree(last_folder_path)
    except: pass
    return True

# ==========================================
# Core Logic Functions
# ==========================================

def check_escape():
    if IJ.escapePressed():
        IJ.resetEscape()
        IJ.log(">>> Operation terminated by user (Esc).")
        return True
    return False

def natural_sort_key(text):
    return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', text)]

# --- Modules ---

def run_roi_crop_tool():
    save_checkpoint()
    imp = IJ.getImage()
    if not imp:
        IJ.showMessage(u"\u63d0\u793a", u"\u6ca1\u6709\u6253\u5f00\u7684\u56fe\u50cf")
        return
    if not imp.getRoi():
        IJ.showMessage(u"\u63d0\u793a", u"\u8bf7\u5148\u5728\u5f53\u524d\u56fe\u50cf\u4e0a\u753b\u4e00\u4e2a\u9009\u533a (ROI)\u3002")
        return
    p = get_roi_prefs()
    msg = u"ROIs \u5df2\u5e94\u7528\u5230\u6240\u6709\u7a97\u53e3\u3002\\n\u8bf7\u68c0\u67e5\u6240\u6709\u7a97\u53e3\u4e0a\u7684 ROI\u3002\\n\u70b9\u51fb OK \u5c06\u5bf9\u6240\u6709\u7a97\u53e3\u6267\u884c Crop\uff08\u4e0d\u53ef\u64a4\u9500\uff09\uff0c\u5173\u95ed\u5bf9\u8bdd\u6846\u5219\u7ee7\u7eed\u3002"
    macro_code = 'run("ROI Manager..."); roiManager("Reset"); roiManager("Add");'
    if p["apply_all"]:
        macro_code += 'n = nImages(); if (n == 0) exit();'
        if p["confirm"]:
            macro_code += """
            for (i = 1; i <= n; i++) { selectImage(i); roiManager("Select", 0); }
            waitForUser("%s");
            """ % msg
        macro_code += 'for (i = 1; i <= n; i++) { selectImage(i); roiManager("Select", 0); run("Crop"); }'
    else:
        if p["confirm"]: macro_code += 'waitForUser("Click OK to Crop CURRENT image.");'
        macro_code += 'run("Crop");'
    try: IJ.runMacro(macro_code)
    except Exception as e: IJ.log("Macro Error: " + str(e))

def run_batch_merge():
    save_checkpoint()
    p = get_merge_prefs()
    ch_str = p["channels"].replace(" ", "")
    if p["confirm"]:
        msg = u"即将对所有图片执行通道融合。\n设置通道: " + ch_str + u"\n \n是否继续？"
        if not IJ.showMessageWithCancel("Confirm Merge", msg): return
    macro_code = """
    setBatchMode(true); n = nImages(); if (n == 0) exit("No open images.");
    target_channels = newArray(%s);
    titles = newArray(n); for (i = 0; i < n; i++) { selectImage(i+1); titles[i] = getTitle(); }
    for (i = 0; i < n; i++) {
        orig = titles[i]; if (isOpen(orig)) {
            selectWindow(orig); run("Split Channels"); existing = newArray(0);
            for (c = 1; c <= 10; c++) {
                candidate = "C" + c + "-" + orig;
                if (isOpen(candidate)) {
                    should_merge = false; for (j=0; j<target_channels.length; j++) if (target_channels[j] == c) should_merge = true;
                    if (should_merge) existing = Array.concat(existing, candidate); else { selectWindow(candidate); close(); }
                }
            }
            if (existing.length > 0) {
                cmd = ""; for (k = 0; k < existing.length; k++) cmd += "c" + (k+1) + "=" + existing[k] + " ";
                cmd += "create"; run("Merge Channels...", cmd); rename(orig);
            }
        }
    }
    setBatchMode("exit and display");
    """ % ch_str
    try: IJ.runMacro(macro_code)
    except Exception as e: IJ.runMacro('setBatchMode("exit and display");')

def calculate_ratio_single(imp_source, d_min, d_max, bar_enabled, ch_num, ch_den):
    img_title = imp_source.getTitle()
    imp_ch1 = Duplicator().run(imp_source, ch_num, ch_num, 1, imp_source.getNSlices(), 1, imp_source.getNFrames())
    imp_ch2 = Duplicator().run(imp_source, ch_den, ch_den, 1, imp_source.getNSlices(), 1, imp_source.getNFrames())
    IJ.run(imp_ch1, "32-bit", ""); IJ.run(imp_ch2, "32-bit", "")
    ic = ImageCalculator(); imp_ratio = ic.run("Divide create 32-bit", imp_ch1, imp_ch2)
    imp_mask = imp_ch2.duplicate(); imp_mask.getProcessor().setAutoThreshold("Otsu dark"); IJ.run(imp_mask, "Create Selection", "")
    roi = imp_mask.getRoi()
    if roi: imp_ratio.setRoi(roi); IJ.run(imp_ratio, "Make Inverse", ""); IJ.run(imp_ratio, "Set...", "value=NaN"); imp_ratio.killRoi()
    imp_ch1.changes=False; imp_ch1.close(); imp_ch2.changes=False; imp_ch2.close(); imp_mask.changes=False; imp_mask.close()
    imp_ratio.setTitle("Ratio_" + img_title)
    IJ.run(imp_ratio, "Fire", "")
    imp_ratio.setDisplayRange(d_min, d_max)
    
    if bar_enabled:
        p = get_ratio_prefs()
        # Construct cmd: location=[Upper Right] fill=White label=Black number=5 decimal=2 font=12 zoom=1 overlay bold show
        b_cmd = "location=[{}] fill={} label={} number={} decimal={} font={} zoom={} overlay".format(
            p["loc"], p["fill"], p["label"], p["n_labels"], p["dec"], p["font"], p["zoom"]
        )
        if p["bold"]: b_cmd += " bold"
        if p["unit"]: b_cmd += " show"
        if not p["overlay"]: b_cmd = b_cmd.replace(" overlay", "") # remove if false, default macro might need logic
        # Actually standard macro command logic:
        # If 'overlay' is in string, it overlays. If not, it burns in.
        
        IJ.run(imp_ratio, "Calibration Bar...", b_cmd)
    
    imp_ratio.show()
    return imp_ratio

def create_separate_legend(d_min, d_max):
    p = get_ratio_prefs()
    imp = NewImage.createFloatImage("Ratio_Legend", 150, 300, 1, NewImage.FILL_WHITE)
    IJ.run(imp, "Fire", ""); imp.setDisplayRange(d_min, d_max); imp.getProcessor().setValue(d_max); imp.getProcessor().fill()
    
    b_cmd = "location=[{}] fill={} label={} number={} decimal={} font={} zoom={}".format(
            p["loc"], p["fill"], p["label"], p["n_labels"], p["dec"], p["font"], p["zoom"]
    )
    if p["bold"]: b_cmd += " bold"
    if p["unit"]: b_cmd += " show"
    
    IJ.run(imp, "Calibration Bar...", b_cmd)
    imp.show()

def run_ratio_analysis():
    save_checkpoint()
    ids = WindowManager.getIDList()
    if not ids: IJ.error("No images open."); return

    p = get_ratio_prefs()
    ch_num = p["num"]; ch_den = p["den"]; d_min = p["min"]; d_max = p["max"]
    do_batch = False 
    
    if p["confirm"]:
        gd = GenericDialog("Run Ratio Analysis")
        gd.addMessage("Open Images: " + str(len(ids)))
        gd.addCheckbox("Apply to ALL open images?", False)
        gd.addNumericField("Min Value:", d_min, 2)
        gd.addNumericField("Max Value:", d_max, 2)
        gd.addNumericField("Numerator Ch:", ch_num, 0)
        gd.addNumericField("Denominator Ch:", ch_den, 0)
        gd.showDialog()
        if gd.wasCanceled(): return
        do_batch = gd.getNextBoolean(); d_min = gd.getNextNumber(); d_max = gd.getNextNumber()
        ch_num = int(gd.getNextNumber()); ch_den = int(gd.getNextNumber())

    originals = []
    if do_batch:
        for i in ids:
            if check_escape(): break
            img = WindowManager.getImage(i)
            if img and "Ratio_" not in img.getTitle() and img.getNChannels() >= max(ch_num, ch_den):
                calculate_ratio_single(img, d_min, d_max, False, ch_num, ch_den)
                originals.append(img)
        if p["add_bar"]: create_separate_legend(d_min, d_max)
    else:
        active = IJ.getImage()
        if active and active.getNChannels() >= max(ch_num, ch_den):
            calculate_ratio_single(active, d_min, d_max, p["add_bar"], ch_num, ch_den)
            originals.append(active)
        else: IJ.error("Active image invalid.")

    IJ.run("Set Measurements...", "mean min redirect=None decimal=3")
    
    if originals and not check_escape():
        gd2 = GenericDialog("Close Originals")
        gd2.addMessage("Close original source images?")
        gd2.setOKLabel("Yes"); gd2.setCancelLabel("No")
        gd2.showDialog()
        if not gd2.wasCanceled():
            for o in originals: o.changes=False; o.close()

def run_scale_bar_and_copy_sequence():
    save_checkpoint()
    ids = WindowManager.getIDList()
    if not ids: IJ.error("Error", "No images open!"); return

    p = get_sb_prefs()
    
    if p["enable_bar"]:
        params = "width={} height={} font={} color={} background={} location=[{}]".format(
            p["width"], p["height"], p["font"], p["color"], p["bg"], p["location"]
        )
        if p["bold"]: params += " bold"
        if p["hide"]: params += " hide"
        if p["overlay"]: params += " overlay"
        
        for id in ids:
            if check_escape(): return
            imp = WindowManager.getImage(id)
            if imp:
                IJ.run(imp, "Scale Bar...", params)
                imp.updateAndDraw()
    
    if p["enable_copy"]:
        titles = sorted(WindowManager.getImageTitles(), key=natural_sort_key)
        count = 0
        for t in titles:
            if check_escape(): return
            count += 1
            img = WindowManager.getImage(t)
            if img:
                img.getWindow().toFront(); img.setPosition(1, img.getSlice(), img.getFrame()); time.sleep(0.15)
                IJ.run(img, "Copy to System", "")
                wd = WaitForUserDialog("Paste Prompt", "Image {} of {}\nName: {}\n\nCopied. Paste then click OK.".format(count, len(titles), t))
                wd.show()
                if wd.escPressed(): return
        gd = GenericDialog("Finished"); gd.addMessage("All images processed.\nClose all open images?"); gd.setOKLabel("Yes"); gd.showDialog()
        if not gd.wasCanceled():
            for i in WindowManager.getIDList(): 
                img = WindowManager.getImage(i); 
                if img: img.changes=False; img.close()
    else:
        if p["enable_bar"]: IJ.showMessage("Scale Bars Added", "Scale bars have been added to all images.")

def run_batch_brightness_tool():
    save_checkpoint()
    ids = WindowManager.getIDList()
    if not ids: return
    gd = GenericDialog("Channel"); gd.addRadioButtonGroup("Channel:", ["1","2","3","4"], 1, 4, "1"); gd.showDialog()
    if gd.wasCanceled(): return
    ch = int(gd.getNextRadioButton())
    for i in ids: 
        img = WindowManager.getImage(i)
        if img and (img.isHyperStack() or img.isComposite()): img.setPosition(ch, img.getSlice(), img.getFrame())
    IJ.run("Brightness/Contrast...")
    wd = WaitForUserDialog("Interactive", "Adjust B&C then Click OK here."); wd.show()
    if wd.escPressed(): return
    gd2 = GenericDialog("Apply"); gd2.addMessage("Apply Min/Max to all?"); gd2.setOKLabel("Yes"); gd2.showDialog()
    if not gd2.wasCanceled():
        src = IJ.getImage(); minv = src.getDisplayRangeMin(); maxv = src.getDisplayRangeMax()
        for i in ids:
            img = WindowManager.getImage(i)
            if img: 
                if img.isHyperStack() or img.isComposite(): img.setPosition(ch, img.getSlice(), img.getFrame())
                img.setDisplayRange(minv, maxv); img.updateAndDraw()
        IJ.showMessage("Done", "Applied.")

# --- Module 6: Smart Undo ---

def run_undo_reload():
    global LAST_DROPPED_FILES
    confirm = get_undo_confirm()
    can_step_back = len(CHECKPOINT_STACK) > 0
    can_reload = len(LAST_DROPPED_FILES) > 0
    
    if confirm:
        gd = GenericDialog("Undo")
        msg = u""
        if can_step_back:
            step_count = len(CHECKPOINT_STACK)
            msg += u"\u53ef\u64a4\u56de\u5230\u4e0a\u4e00\u6b65\u3010Step Back\u3011\u3002\n(Stack Size: " + str(step_count) + ")"
            btn_lbl = "Undo Last Step"
        elif can_reload:
            msg += u"\u65e0\u6b65\u6570\u53ef\u64a4\u56de\u3002\n\u662f\u5426\u91cd\u65b0\u52a0\u8f7d\u6e90\u6587\u4ef6\uff1f"
            btn_lbl = "Reload Original"
        else:
            IJ.showMessage("Undo", u"\u6ca1\u6709\u5386\u53f2\u8bb0\u5f55\u3002")
            return
        gd.addMessage(msg); gd.setOKLabel(btn_lbl); gd.showDialog()
        if gd.wasCanceled(): return
    
    if can_step_back:
        success = restore_last_checkpoint()
        if not success and can_reload:
            if confirm and not IJ.showMessageWithCancel("Warning", "Checkpoint missing. Reload originals?"): return
            reload_originals()
    elif can_reload:
        reload_originals()

def reload_originals():
    global LAST_DROPPED_FILES
    ids = WindowManager.getIDList()
    if ids:
        for id in ids:
            imp = WindowManager.getImage(id); 
            if imp: imp.changes=False; imp.close()
    for path in LAST_DROPPED_FILES:
        try: IJ.run("Bio-Formats Importer", "open=[" + path.replace("\\","\\\\") + "] autoscale color_mode=Colorized view=Hyperstack stack_order=XYCZT")
        except: pass

def run_close_all_no_save():
    save_checkpoint()
    ids = WindowManager.getIDList()
    if not ids: return
    gd = GenericDialog("Close All"); gd.addMessage("Close ALL images?"); gd.setOKLabel("Close"); gd.showDialog()
    if not gd.wasCanceled():
        for i in ids:
            img = WindowManager.getImage(i); 
            if img: img.changes=False; img.close()

# ==========================================
# Drag & Drop
# ==========================================
class BioFormatsDropListener(DropTargetAdapter):
    def drop(self, dtde):
        dtde.acceptDrop(DnDConstants.ACTION_COPY)
        t = dtde.getTransferable()
        if t.isDataFlavorSupported(DataFlavor.javaFileListFlavor):
            files = t.getTransferData(DataFlavor.javaFileListFlavor)
            global LAST_DROPPED_FILES; LAST_DROPPED_FILES = []
            for f in files: LAST_DROPPED_FILES.append(f.getAbsolutePath())
            
            cleanup_all_checkpoints()
            ensure_checkpoint_root()
            
            def worker():
                for f in files:
                    try: IJ.run("Bio-Formats Importer", "open=[" + f.getAbsolutePath().replace("\\","\\\\") + "] autoscale color_mode=Colorized view=Hyperstack stack_order=XYCZT")
                    except: pass
                time.sleep(1.0)
                save_checkpoint()
            threading.Thread(target=worker).start()
            dtde.dropComplete(True)
        else: dtde.rejectDrop()

# ==========================================
# GUI Construction
# ==========================================

class ToolboxCloseListener(WindowAdapter):
    def windowClosing(self, event):
        cleanup_all_checkpoints()
        event.getSource().dispose()

class ToolboxGUI(JFrame):
    def __init__(self):
        super(ToolboxGUI, self).__init__("Cell Toolbox v2.24")
        self.setSize(240, 480)
        self.setAlwaysOnTop(True)
        self.setDefaultCloseOperation(JFrame.DO_NOTHING_ON_CLOSE)
        self.addWindowListener(ToolboxCloseListener())
        
        main_panel = JPanel()
        main_panel.setLayout(BoxLayout(main_panel, BoxLayout.Y_AXIS))
        main_panel.setBorder(BorderFactory.createEmptyBorder(10, 10, 10, 10))
        self.drop_target = DropTarget(main_panel, BioFormatsDropListener())
        
        lbl = JLabel("ImageJ Tools for Xiaoming")
        lbl.setFont(Font("SansSerif", Font.BOLD, 14))
        lbl.setAlignmentX(Component.CENTER_ALIGNMENT)
        main_panel.add(lbl)
        main_panel.add(JSeparator())
        main_panel.add(Box.createRigidArea(Dimension(0, 5)))
        
        def add_module_row(btn_text, action_func, settings_func=None, btn_color=None):
            row = JPanel(BorderLayout(5, 0))
            row.setMaximumSize(Dimension(220, 35))
            row.setAlignmentX(Component.CENTER_ALIGNMENT)
            
            btn = JButton(btn_text)
            btn.setFont(Font("SansSerif", Font.PLAIN, 12))
            if btn_color: btn.setForeground(btn_color)
            btn.addActionListener(lambda e: threading.Thread(target=action_func).start())
            row.add(btn, BorderLayout.CENTER)
            
            cfg_btn = JButton(u"\u2699") 
            cfg_btn.setFont(Font("SansSerif", Font.PLAIN, 14))
            cfg_btn.setMargin(Insets(2, 2, 2, 2))
            cfg_btn.setPreferredSize(Dimension(30, 35))
            
            if settings_func:
                def safe_settings_run():
                    try: settings_func()
                    except Exception as e: IJ.log("Settings Error: " + str(e))
                cfg_btn.addActionListener(lambda e: threading.Thread(target=safe_settings_run).start())
            else:
                cfg_btn.addActionListener(lambda e: threading.Thread(target=lambda: show_settings_placeholder(btn_text)).start())
                
            row.add(cfg_btn, BorderLayout.EAST)
            main_panel.add(row)
            main_panel.add(Box.createRigidArea(Dimension(0, 5)))

        add_module_row("1. Apply ROI & Crop", run_roi_crop_tool, show_roi_settings)
        add_module_row("2. Batch Merge", run_batch_merge, show_merge_settings)
        add_module_row("3. Ratio Analysis", run_ratio_analysis, show_ratio_settings)
        add_module_row("4. Scale Bar & Copy", run_scale_bar_and_copy_sequence, show_scalebar_settings)
        add_module_row("5. Batch Brightness", run_batch_brightness_tool)
        main_panel.add(JSeparator())
        main_panel.add(Box.createRigidArea(Dimension(0, 5)))
        add_module_row("6. Smart Undo", run_undo_reload, show_undo_settings, Color.BLUE.darker())
        add_module_row("7. Close All", run_close_all_no_save, None, Color.RED.darker())
        main_panel.add(JSeparator())
        
        drop_lbl = JLabel("Drag Images Here", SwingConstants.CENTER)
        drop_lbl.setForeground(Color.BLUE.darker())
        drop_pnl = JPanel(BorderLayout()); 
        drop_pnl.setBorder(BorderFactory.createStrokeBorder(BasicStroke(1.0, BasicStroke.CAP_BUTT, BasicStroke.JOIN_MITER, 10.0, [5.0], 0.0), Color.GRAY))
        drop_pnl.setMaximumSize(Dimension(220, 40)); drop_pnl.add(drop_lbl, BorderLayout.CENTER)
        DropTarget(drop_pnl, BioFormatsDropListener())
        main_panel.add(Box.createRigidArea(Dimension(0, 5)))
        main_panel.add(drop_pnl)

        self.add(main_panel)
        self.setLocation(10, 100)
        self.setVisible(True)

if __name__ in ['__main__', '__builtin__']:
    cleanup_all_checkpoints()
    ToolboxGUI()