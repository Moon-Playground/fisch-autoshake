#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")] // hide console window on Windows in release

use eframe::egui;
use std::sync::{Arc, atomic::{AtomicBool, Ordering}};
use parking_lot::Mutex;
use crossbeam_channel::Receiver;
use global_hotkey::{GlobalHotKeyManager, hotkey::{HotKey, Code}, GlobalHotKeyEvent};

mod config;
mod detect;

use config::{AppConfig, save_config, load_config};
use detect::start_capture_thread;

struct AutoShakeApp {
    config: Arc<Mutex<AppConfig>>,
    active: Arc<AtomicBool>,
    
    // UI state
    status_msg: String,
    hotkey_manager: GlobalHotKeyManager,
    hotkey_receiver: Receiver<GlobalHotKeyEvent>,
    
    // Config UI state (buffers)
    hk_toggle_box: String,
    hk_toggle_action: String,
    hk_exit_app: String,
    overlay_enabled: bool,
    
    show_capture_box: bool,
}

impl AutoShakeApp {
    fn new(_cc: &eframe::CreationContext<'_>) -> Self {
        // Load config
        let config_data = load_config();
        
        let active = Arc::new(AtomicBool::new(false));
        let config = Arc::new(Mutex::new(config_data.clone()));

        // Start detection thread
        start_capture_thread(active.clone(), config.clone());

        let hotkey_manager = GlobalHotKeyManager::new().unwrap();
        let hotkey_receiver = GlobalHotKeyEvent::receiver().clone();

        let app = Self {
            config,
            active,
            status_msg: "Status: Inactive".to_string(),
            hotkey_manager,
            hotkey_receiver,
            hk_toggle_box: config_data.hotkeys.toggle_box.clone(),
            hk_toggle_action: config_data.hotkeys.toggle_action.clone(),
            hk_exit_app: config_data.hotkeys.exit_app.clone(),
            overlay_enabled: config_data.ui.enable_overlay,
            show_capture_box: false,
        };
        
        app.register_hotkeys(&config_data.hotkeys);
        app
    }

    fn register_hotkeys(&self, hk_config: &config::HotkeysConfig) {
        // Clear all first? The manager doesn't strictly support clear_all easily without tracking IDs
        // For simplicity, we assume this is called once or we accept potential duplicates if we don't unregister.
        // In a real app we should track registered IDs.
        
        let _ = self.hotkey_manager.register(parse_hotkey(&hk_config.toggle_box));
        let _ = self.hotkey_manager.register(parse_hotkey(&hk_config.toggle_action));
        let _ = self.hotkey_manager.register(parse_hotkey(&hk_config.exit_app));
    }

    fn handle_hotkeys(&mut self) {
        while let Ok(event) = self.hotkey_receiver.try_recv() {
            if event.state == global_hotkey::HotKeyState::Released {
                // Find which key it was
                let cfg = self.config.lock();
                
                // Identify by reconstructing IDs or simple comparison (not efficient but works for 3 keys)
                // For now, we trust the ID matches what we registered? 
                // Wait, event.id is a u32. 'register' returns result.
                // We need to store the IDs if we want to match exactly.
                // Or we can rebuild the HotKey from config and check ID.
                
                let h_box = parse_hotkey(&cfg.hotkeys.toggle_box);
                let h_act = parse_hotkey(&cfg.hotkeys.toggle_action);
                let h_exit = parse_hotkey(&cfg.hotkeys.exit_app);
                
                if event.id == h_box.id() {
                   self.show_capture_box = !self.show_capture_box;
                } else if event.id == h_act.id() {
                    let new_state = !self.active.load(Ordering::Relaxed);
                    self.active.store(new_state, Ordering::Relaxed);
                    self.status_msg = if new_state { "Status: Active".to_string() } else { "Status: Inactive".to_string() };
                } else if event.id == h_exit.id() {
                    std::process::exit(0);
                }
            }
        }
    }
}

impl eframe::App for AutoShakeApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.handle_hotkeys();
        ctx.request_repaint(); // Poll continuously for hotkeys? Or wait for event?
        // polling is safe enough for low CPU if we don't do heavy work.
        // But ideally we'd wake up only on event. `global-hotkey` uses a separate thread, does it wake winit?
        // Not necessarily. request_repaint is safest.

        // --- Main Window ---
         egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading("Auto Shake RS");
            ui.label("Simple Auto Shake for roblox fisch (Navigation Mode)");
            
            ui.add_space(10.0);
            
            if self.active.load(Ordering::Relaxed) {
                ui.colored_label(egui::Color32::GREEN, &self.status_msg);
            } else {
                ui.colored_label(egui::Color32::RED, &self.status_msg);
            }
            
            ui.add_space(20.0);
            
            // Settings
            ui.collapsing("Settings", |ui| {
                ui.horizontal(|ui| {
                    ui.label("Toggle Box:");
                    ui.text_edit_singleline(&mut self.hk_toggle_box);
                });
                ui.horizontal(|ui| {
                    ui.label("Toggle Action:");
                    ui.text_edit_singleline(&mut self.hk_toggle_action);
                });
                ui.horizontal(|ui| {
                    ui.label("Exit App:");
                    ui.text_edit_singleline(&mut self.hk_exit_app);
                });
                 ui.horizontal(|ui| {
                    ui.label("Enable Overlay:");
                    ui.checkbox(&mut self.overlay_enabled, "");
                });
                
                if ui.button("Save & Apply").clicked() {
                    let mut cfg = self.config.lock();
                    cfg.hotkeys.toggle_box = self.hk_toggle_box.clone();
                    cfg.hotkeys.toggle_action = self.hk_toggle_action.clone();
                    cfg.hotkeys.exit_app = self.hk_exit_app.clone();
                    cfg.ui.enable_overlay = self.overlay_enabled;
                    save_config(&cfg);
                    // Re-register hotkeys? (Ideally unregister old ones first)
                    // ignoring for MVP
                    self.register_hotkeys(&cfg.hotkeys); 
                }
            });
            
             ui.add_space(10.0);
             if ui.button("Show/Hide Capture Box").clicked() {
                 self.show_capture_box = !self.show_capture_box;
             }
        });

        // --- Capture Box Viewport ---
        if self.show_capture_box {
            let (cx, cy, cw, ch) = {
                let cfg = self.config.lock();
                (cfg.ocr.capture_x, cfg.ocr.capture_y, cfg.ocr.capture_width, cfg.ocr.capture_height)
            };
            
            ctx.show_viewport_immediate(
                egui::ViewportId::from_hash_of("capture_box"),
                egui::ViewportBuilder::default()
                    .with_title("Capture Box")
                    .with_decorations(false)
                    .with_transparent(true)
                    .with_always_on_top()
                    .with_taskbar(false)
                    .with_position([cx as f32, cy as f32])
                    .with_inner_size([cw as f32, ch as f32]),
                |ctx, class| {
                    // Custom resize/move logic if we want, or just a colored box
                    // Since it's transparent, we draw a semi-transparent rect
                    let panel = egui::CentralPanel::default().frame(egui::Frame {
                        fill: egui::Color32::from_rgba_unmultiplied(0, 100, 255, 30), // Subtle blue tint
                        stroke: egui::Stroke::new(2.0, egui::Color32::from_rgba_unmultiplied(0, 100, 255, 200)), // Distinct border
                        rounding: egui::Rounding::same(4.0),
                        ..Default::default()
                    });
                    
                    panel.show(ctx, |ui| {
                        // Move window on drag
                        if ui.input(|i| i.pointer.button_down(egui::PointerButton::Primary)) {
                             ctx.send_viewport_cmd(egui::ViewportCommand::StartDrag);
                        }
                        
                        // Just a label
                        ui.centered_and_justified(|ui| {
                            ui.label(egui::RichText::new("Capture Area").color(egui::Color32::WHITE));
                        });
                        
                        // We need to update config if moved/resized
                        // eframe doesn't easily give us the "moved" event inside immediate mode without querying
                        // But we can query window info?
                        // Actually, 'ctx.input(|i| i.screen_rect())' inside a viewport gives the viewport rect?
                    });
                    
                    // Check if moved
                     if let Some(pos) = ctx.input(|i| i.viewport().outer_rect) {
                         // Update config continuously? Might be spammy.
                         // Only update if changed.
                         let nx = pos.min.x as i32;
                         let ny = pos.min.y as i32;
                         let nw = pos.width() as u32;
                         let nh = pos.height() as u32;
                         
                         let mut changed = false;
                         {
                             let mut cfg = self.config.lock();
                             if cfg.ocr.capture_x != nx || cfg.ocr.capture_y != ny {
                                 cfg.ocr.capture_x = nx;
                                 cfg.ocr.capture_y = ny;
                                 changed = true;
                             }
                             // Resize is not handled here yet (needs custom handle)
                         }
                         if changed {
                            // save_config? Maybe only on close or periodically?
                             let cfg = self.config.lock().clone();
                             // save_config(&cfg); // Don't save on every drag frame!
                         }
                     }
                }
            );
        }

        // --- Status Overlay Viewport ---
        let enable_overlay = self.config.lock().ui.enable_overlay;
        if enable_overlay {
             let (sx, sy) = {
                let cfg = self.config.lock();
                (cfg.ui.status_x, cfg.ui.status_y)
            };
            
            ctx.show_viewport_immediate(
                egui::ViewportId::from_hash_of("status_overlay"),
                egui::ViewportBuilder::default()
                    .with_title("Status")
                    .with_decorations(false)
                    .with_transparent(true)
                    .with_always_on_top()
                    .with_taskbar(false)
                    .with_position([sx as f32, sy as f32])
                    .with_inner_size([150.0, 30.0]),
                |ctx, class| {
                     egui::CentralPanel::default().frame(egui::Frame {
                        fill: egui::Color32::from_black_alpha(200),
                        rounding: egui::Rounding::same(5.0),
                        ..Default::default()
                    }).show(ctx, |ui| {
                         if ui.input(|i| i.pointer.button_down(egui::PointerButton::Primary)) {
                             ctx.send_viewport_cmd(egui::ViewportCommand::StartDrag);
                        }
                        ui.centered_and_justified(|ui| {
                            if self.active.load(Ordering::Relaxed) {
                                ui.label(egui::RichText::new("AutoShake: Active").color(egui::Color32::GREEN).strong());
                            } else {
                                ui.label(egui::RichText::new("AutoShake: Paused").color(egui::Color32::RED).strong());
                            }
                        });
                    });
                     // Save pos update logic similar to capture box...
                }
            );
        }
    }
    
    // On exit
    fn on_exit(&mut self, _gl: Option<&eframe::glow::Context>) {
        let cfg = self.config.lock();
        save_config(&cfg);
    }
}

// Helper to parse "F3" or "A" to HotKey
fn parse_hotkey(s: &str) -> HotKey {
    let s = s.trim().to_uppercase();
    let code = match s.as_str() {
        "F1" => Code::F1, "F2" => Code::F2, "F3" => Code::F3, "F4" => Code::F4, "F5" => Code::F5,
        "F6" => Code::F6, "F7" => Code::F7, "F8" => Code::F8, "F9" => Code::F9, "F10" => Code::F10,
        "F11" => Code::F11, "F12" => Code::F12,
        "ENTER" => Code::Enter, "SPACE" => Code::Space,
        // ... add more if needed
        c if c.len() == 1 => {
             // Dumb mapping for A-Z
             match c.chars().next().unwrap() {
                 'A' => Code::KeyA, 'B' => Code::KeyB, 'C' => Code::KeyC, 'D' => Code::KeyD,
                 'E' => Code::KeyE, 'F' => Code::KeyF, 'G' => Code::KeyG, 'H' => Code::KeyH,
                 'I' => Code::KeyI, 'J' => Code::KeyJ, 'K' => Code::KeyK, 'L' => Code::KeyL,
                 'M' => Code::KeyM, 'N' => Code::KeyN, 'O' => Code::KeyO, 'P' => Code::KeyP,
                 'Q' => Code::KeyQ, 'R' => Code::KeyR, 'S' => Code::KeyS, 'T' => Code::KeyT,
                 'U' => Code::KeyU, 'V' => Code::KeyV, 'W' => Code::KeyW, 'X' => Code::KeyX,
                 'Y' => Code::KeyY, 'Z' => Code::KeyZ,
                 _ => Code::F3, // Fallback
             }
        }
        _ => Code::F3, // Default fallback
    };
    HotKey::new(None, code) // No modifiers for now
}


fn load_icon() -> Option<egui::IconData> {
    if let Ok(image) = image::open("res/icon.ico") {
        let image = image.into_rgba8();
        let (width, height) = image.dimensions();
        let rgba = image.into_raw();
        Some(egui::IconData {
            rgba,
            width,
            height,
        })
    } else {
        None
    }
}

fn main() -> eframe::Result<()> {
    env_logger::init();
    
    let mut viewport = egui::ViewportBuilder::default()
        .with_inner_size([600.0, 400.0])
        .with_title("Auto Shake RS")
        .with_transparent(true);

    if let Some(icon) = load_icon() {
        viewport = viewport.with_icon(std::sync::Arc::new(icon));
    }

    let options = eframe::NativeOptions {
        viewport,
        ..Default::default()
    };
    
    eframe::run_native(
        "Auto Shake RS",
        options,
        Box::new(|_cc| Ok(Box::new(AutoShakeApp::new(_cc)))),
    )
}
