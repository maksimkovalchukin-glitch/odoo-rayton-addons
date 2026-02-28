/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { useService } from "@web/core/utils/hooks";
import { onMounted, onWillUnmount } from "@odoo/owl";

// ─── Helpers ────────────────────────────────────────────────────────────────

function getInitials(name) {
    return (name || "?")
        .split(" ")
        .map(w => w[0] || "")
        .join("")
        .slice(0, 2)
        .toUpperCase();
}

function formatTime(iso) {
    if (!iso) return "";
    try {
        return new Date(iso).toLocaleString("uk-UA", {
            hour: "2-digit", minute: "2-digit",
        });
    } catch { return ""; }
}

function formatDateLabel(iso) {
    if (!iso) return "";
    try {
        return new Date(iso).toLocaleDateString("uk-UA", {
            day: "2-digit", month: "long", year: "numeric",
        });
    } catch { return ""; }
}

function stripHtml(html) {
    const d = document.createElement("div");
    d.innerHTML = html || "";
    return d.textContent || d.innerText || "";
}

function buildAvatarHtml(partnerId, initials) {
    if (!partnerId) {
        return `<div class="o_rayton_avatar">${initials}</div>`;
    }
    return `<div class="o_rayton_avatar o_rayton_avatar_has_img" data-initials="${initials}">` +
        `<img src="/web/image/res.partner/${partnerId}/avatar_128" alt="${initials}" class="o_rayton_avatar_img" ` +
        `onerror="this.remove();this.parentNode.textContent=this.parentNode.dataset.initials;this.parentNode.classList.remove('o_rayton_avatar_has_img')"/>` +
        `</div>`;
}

// ─── Panel Manager ───────────────────────────────────────────────────────────

class RaytonPanelManager {
    constructor(orm, action) {
        this.orm = orm;
        this.action = action;
        this.panelWidth = 390;
        this._open = false;
        this._channelId = null;
        this._channelName = "";
        this._projectId = null;

        this._toggle = null;
        this._panel = null;
        this._messagesEl = null;
        this._inputEl = null;
        this._sendBtn = null;

        this._resizing = false;
        this._resizeStartX = 0;
        this._resizeStartW = 390;
        this._pollInterval = null;
        this._lastRenderedMsgId = null;
        this._backdrop = null;

        this._onMouseMove = this._onMouseMove.bind(this);
        this._onMouseUp = this._onMouseUp.bind(this);
        window.addEventListener("mousemove", this._onMouseMove);
        window.addEventListener("mouseup", this._onMouseUp);

        // iOS Safari: resize panel to visual viewport height so the composer
        // stays above the browser bottom bar and the on-screen keyboard
        this._onViewportChange = null;
        if (window.visualViewport) {
            this._onViewportChange = () => {
                if (!this._panel) return;
                const vv = window.visualViewport;
                this._panel.style.height = Math.round(vv.height) + "px";
                this._panel.style.top = Math.round(vv.offsetTop) + "px";
            };
            window.visualViewport.addEventListener("resize", this._onViewportChange);
            window.visualViewport.addEventListener("scroll", this._onViewportChange);
        }
    }

    async init(projectId) {
        this._projectId = projectId;
        if (!projectId) return;

        try {
            // action_get_channel_info also auto-joins the user as a channel member
            // so they can read and send messages (fixes existing linked channel issue)
            const result = await this.orm.call(
                "project.project", "action_get_channel_info",
                [projectId], {}
            );
            if (result) {
                this._channelId = result.channel_id || null;
                this._channelName = result.channel_name || "";
            }
        } catch (e) {
            console.warn("[RaytonHub] Failed to load project channel info:", e);
        }

        this._mountDOM();
    }

    _mountDOM() {
        // Backdrop — tapping it closes the panel on mobile
        const backdrop = document.createElement("div");
        backdrop.className = "o_rayton_backdrop";
        // Use touchstart so the response is instant on mobile
        backdrop.addEventListener("touchstart", (e) => {
            e.preventDefault();
            this.togglePanel();
        }, { passive: false });
        backdrop.addEventListener("click", () => this.togglePanel());
        document.body.appendChild(backdrop);
        this._backdrop = backdrop;

        // Toggle button
        const toggle = document.createElement("button");
        toggle.className = "o_rayton_panel_toggle";
        toggle.title = "Обговорення проекту";
        toggle.innerHTML = `<span class="o_toggle_icon">💬</span><span>Чат</span>`;
        // touchstart fires immediately on mobile (no 300ms delay); preventDefault
        // stops the browser from also firing a click event afterward
        toggle.addEventListener("touchstart", (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.togglePanel();
        }, { passive: false });
        toggle.addEventListener("click", () => this.togglePanel());
        document.body.appendChild(toggle);
        this._toggle = toggle;

        // Panel container
        const panel = document.createElement("div");
        panel.className = "o_rayton_discussion_panel";
        document.body.appendChild(panel);
        this._panel = panel;

        this._renderPanelContent();
    }

    _renderPanelContent() {
        const panel = this._panel;
        if (!panel) return;

        const ch = this._channelId;
        const chName = this._channelName;

        const bodyContent = ch
            ? `<div class="o_rayton_messages"></div>
               <div class="o_rayton_composer">
                   <textarea class="o_rayton_composer_input"
                       placeholder="Написати повідомлення... (Enter — надіслати)"
                       rows="1"></textarea>
                   <button class="o_rayton_send_btn" title="Надіслати">➤</button>
               </div>`
            : `<div class="o_rayton_empty">
                   <i class="fa fa-comments-o" style="font-size:44px;opacity:0.3;"></i>
                   <p>До цього проекту не прив'язано канал.</p>
                   <button class="o_rayton_create_channel_btn">+ Створити канал</button>
                   <a href="#" class="o_rayton_settings_link">або прив'язати існуючий</a>
               </div>`;

        panel.innerHTML = `
            <div class="o_rayton_panel_resize"></div>
            <div class="o_rayton_panel_header">
                <div class="o_rayton_panel_header_info">
                    <div class="o_rayton_panel_header_title"
                         title="${ch ? 'Відкрити в Discuss ↗' : ''}">
                        💬 Обговорення проекту${ch ? ' ↗' : ''}
                    </div>
                    ${chName ? `<div class="o_rayton_panel_header_sub"># ${chName}</div>` : ""}
                </div>
                <button class="o_rayton_panel_close" title="Закрити">✕</button>
            </div>
            <div class="o_rayton_panel_body">${bodyContent}</div>
        `;

        // Wire close button — touchstart for instant mobile response
        const closeBtn = panel.querySelector(".o_rayton_panel_close");
        if (closeBtn) {
            closeBtn.addEventListener("touchstart", (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.togglePanel();
            }, { passive: false });
            closeBtn.addEventListener("click", () => this.togglePanel());
        }

        // Wire header title click → navigate to Discuss channel (via action service)
        if (this._channelId) {
            panel.querySelector(".o_rayton_panel_header_title")
                ?.addEventListener("click", () => {
                    this.action.doAction({
                        type: "ir.actions.client",
                        tag: "mail.action_discuss",
                    }, {
                        additionalContext: {
                            active_id: `discuss.channel_${this._channelId}`,
                        },
                    });
                });
        }

        // Wire resize handle
        panel.querySelector(".o_rayton_panel_resize")
            ?.addEventListener("mousedown", (e) => {
                this._resizing = true;
                this._resizeStartX = e.clientX;
                this._resizeStartW = this.panelWidth;
                panel.querySelector(".o_rayton_panel_resize").classList.add("resizing");
                e.preventDefault();
            });

        // Cache refs
        this._messagesEl = panel.querySelector(".o_rayton_messages");
        this._inputEl = panel.querySelector(".o_rayton_composer_input");
        this._sendBtn = panel.querySelector(".o_rayton_send_btn");

        // Wire composer
        if (this._inputEl) {
            this._inputEl.addEventListener("input", () => {
                this._inputEl.style.height = "auto";
                this._inputEl.style.height = Math.min(this._inputEl.scrollHeight, 120) + "px";
            });
            this._inputEl.addEventListener("keydown", (e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }
        if (this._sendBtn) {
            this._sendBtn.addEventListener("click", () => this.sendMessage());
        }

        // Wire "create channel" button
        panel.querySelector(".o_rayton_create_channel_btn")
            ?.addEventListener("click", () => this._createChannel());

        // Wire "link existing" link
        panel.querySelector(".o_rayton_settings_link")
            ?.addEventListener("click", (e) => {
                e.preventDefault();
                this._openProjectSettings();
            });
    }

    async _createChannel() {
        if (!this._projectId) return;
        const btn = this._panel.querySelector(".o_rayton_create_channel_btn");
        if (btn) { btn.disabled = true; btn.textContent = "Створення..."; }

        try {
            const result = await this.orm.call(
                "project.project", "action_create_discuss_channel",
                [this._projectId], {}
            );
            if (result && result.channel_id) {
                this._channelId = result.channel_id;
                this._channelName = result.channel_name || "";
                this._renderPanelContent();
                if (this._open) await this._loadMessages();
            }
        } catch (e) {
            console.warn("[RaytonHub] Failed to create channel:", e);
            if (btn) { btn.disabled = false; btn.textContent = "+ Створити канал"; }
        }
    }

    _isMobile() {
        return window.matchMedia("(max-width: 768px)").matches;
    }

    togglePanel() {
        this._open = !this._open;
        const mobile = this._isMobile();

        if (this._open) {
            this._panel.style.width = mobile ? "100vw" : this.panelWidth + "px";
            this._panel.classList.add("open");
            if (this._toggle) {
                this._toggle.innerHTML = `<span class="o_toggle_icon">❮</span>`;
                // On mobile: toggle stays at right:0 — CSS gives it z-index:1070
                // so it sits above the panel (1060) and is always tappable
                if (!mobile) {
                    this._toggle.style.right = this.panelWidth + "px";
                }
            }
            // Show backdrop on mobile so tapping outside the toggle also closes
            if (mobile && this._backdrop) {
                this._backdrop.classList.add("active");
            }
            this._shiftContent(true);
            if (this._channelId) {
                this._loadMessages();
                // Auto-refresh every 8 seconds (silent — no spinner flash)
                this._pollInterval = setInterval(() => this._loadMessages(true), 8000);
            }
        } else {
            this._panel.classList.remove("open");
            this._panel.style.width = "0";
            if (this._toggle) {
                this._toggle.innerHTML = `<span class="o_toggle_icon">💬</span><span>Чат</span>`;
                this._toggle.style.right = "0px";
            }
            if (this._backdrop) {
                this._backdrop.classList.remove("active");
            }
            this._shiftContent(false);
            if (this._pollInterval) {
                clearInterval(this._pollInterval);
                this._pollInterval = null;
            }
        }
    }

    _shiftContent(open) {
        if (this._isMobile()) return; // panel is overlay on mobile — no content shift
        const el = document.querySelector(".o_action_manager > .o_action");
        if (!el) return;
        el.style.transition = "margin-right 0.32s cubic-bezier(0.4, 0, 0.2, 1)";
        el.style.marginRight = open ? this.panelWidth + "px" : "0px";
    }

    async _loadMessages(silent = false) {
        if (!this._channelId || !this._messagesEl) return;

        // Show spinner only on first (non-silent) load
        if (!silent) {
            this._messagesEl.innerHTML = `
                <div class="o_rayton_loading">
                    <div class="o_rayton_spinner"></div>
                    <span>Завантаження...</span>
                </div>`;
        }

        try {
            // order: "date desc" + limit to get the LATEST 60 messages,
            // then reverse so they display oldest-first in the panel
            const messages = await this.orm.searchRead(
                "mail.message",
                [
                    ["res_id", "=", this._channelId],
                    ["model", "=", "discuss.channel"],
                    ["message_type", "in", ["comment", "email"]],
                ],
                ["id", "author_id", "body", "date"],
                { limit: 60, order: "date desc" }
            );
            messages.reverse();

            // Silent refresh: skip full DOM rebuild if nothing changed
            const lastId = messages.length ? messages[messages.length - 1].id : null;
            if (silent && lastId === this._lastRenderedMsgId) return;
            this._lastRenderedMsgId = lastId;

            this._messagesEl.innerHTML = "";

            if (!messages.length) {
                this._messagesEl.innerHTML = `
                    <div class="o_rayton_empty">
                        <i class="fa fa-comment-o" style="font-size:36px;opacity:0.3;"></i>
                        <p>Повідомлень ще немає.<br/>Напишіть першим! 👋</p>
                    </div>`;
                return;
            }

            let lastDateLabel = "";
            let lastAuthorId = null;

            messages.forEach(msg => {
                // ── Date divider ──────────────────────────────────────────────
                const dateLabel = formatDateLabel(msg.date);
                if (dateLabel && dateLabel !== lastDateLabel) {
                    lastDateLabel = dateLabel;
                    lastAuthorId = null; // reset grouping on new date
                    const div = document.createElement("div");
                    div.className = "o_rayton_date_divider";
                    div.textContent = dateLabel;
                    this._messagesEl.appendChild(div);
                }

                // ── Message grouping ──────────────────────────────────────────
                const authorId = msg.author_id ? msg.author_id[0] : null;
                const isContinuation = authorId && authorId === lastAuthorId;
                lastAuthorId = authorId;

                const author = msg.author_id ? msg.author_id[1] : "Невідомий";
                const initials = getInitials(author);
                const time = formatTime(msg.date);
                const body = stripHtml(msg.body);

                const el = document.createElement("div");

                if (isContinuation) {
                    // Same author → no avatar, no name, compact
                    el.className = "o_rayton_message o_rayton_continuation";
                    el.innerHTML = `
                        <div class="o_rayton_avatar_gap"></div>
                        <div class="o_rayton_msg_content">
                            <div class="o_rayton_msg_body">${body}</div>
                        </div>`;
                } else {
                    // New author → show avatar photo + name + time
                    el.className = "o_rayton_message";
                    el.innerHTML = `
                        ${buildAvatarHtml(authorId, initials)}
                        <div class="o_rayton_msg_content">
                            <div class="o_rayton_msg_meta">
                                <span class="o_rayton_msg_author">${author}</span>
                                <span class="o_rayton_msg_time">${time}</span>
                            </div>
                            <div class="o_rayton_msg_body">${body}</div>
                        </div>`;
                }

                this._messagesEl.appendChild(el);
            });

            this._messagesEl.scrollTop = this._messagesEl.scrollHeight;
        } catch (e) {
            console.warn("[RaytonHub] Failed to load messages:", e);
            this._messagesEl.innerHTML = `
                <div class="o_rayton_empty">
                    <p>Помилка завантаження.<br/>
                    <a href="/odoo/discuss?default_active_id=discuss.channel_${this._channelId}"
                       target="_blank">Відкрити в Discuss ↗</a></p>
                </div>`;
        }
    }

    async sendMessage() {
        if (!this._inputEl || !this._channelId) return;
        const body = this._inputEl.value.trim();
        if (!body) return;

        if (this._sendBtn) {
            this._sendBtn.disabled = true;
            this._sendBtn.style.opacity = "0.4";
        }

        try {
            await this.orm.call("discuss.channel", "message_post", [this._channelId], {
                body: body,
                message_type: "comment",
                subtype_xmlid: "mail.mt_comment",
            });
            this._inputEl.value = "";
            this._inputEl.style.height = "auto";
            await this._loadMessages();
        } catch (e) {
            console.warn("[RaytonHub] Failed to send message:", e);
            alert("Не вдалося надіслати повідомлення. Спробуйте ще раз.");
        } finally {
            if (this._sendBtn) {
                this._sendBtn.disabled = false;
                this._sendBtn.style.opacity = "1";
            }
        }
    }

    async _openProjectSettings() {
        if (!this._projectId) return;
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.project",
            res_id: this._projectId,
            views: [[false, "form"]],
            target: "new",
        });
    }

    _onMouseMove(e) {
        if (!this._resizing) return;
        const delta = this._resizeStartX - e.clientX;
        const newW = Math.max(280, Math.min(720, this._resizeStartW + delta));
        this.panelWidth = newW;
        if (this._panel) {
            this._panel.style.width = newW + "px";
        }
        if (this._toggle && this._open) {
            this._toggle.style.right = newW + "px";
        }
        this._shiftContent(this._open);
    }

    _onMouseUp() {
        if (this._resizing) {
            this._resizing = false;
            this._panel?.querySelector(".o_rayton_panel_resize")
                ?.classList.remove("resizing");
        }
    }

    destroy() {
        if (this._pollInterval) {
            clearInterval(this._pollInterval);
            this._pollInterval = null;
        }
        window.removeEventListener("mousemove", this._onMouseMove);
        window.removeEventListener("mouseup", this._onMouseUp);
        if (window.visualViewport && this._onViewportChange) {
            window.visualViewport.removeEventListener("resize", this._onViewportChange);
            window.visualViewport.removeEventListener("scroll", this._onViewportChange);
        }
        this._shiftContent(false);
        this._backdrop?.remove();
        this._toggle?.remove();
        this._panel?.remove();
    }
}

// ─── Patch KanbanController — show chat panel in kanban task view ────────────
// Note: NO redirect to list — user can switch views freely.
// The action's view_mode='list,kanban,form' already ensures list is default
// when the project is opened from CRM or the wizard.

patch(KanbanController.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.action = useService("action");
        this._raytonPanel = null;

        onMounted(async () => {
            if (this._isProjectTaskView()) {
                const projectId = this._getProjectId();
                if (projectId) {
                    this._raytonPanel = new RaytonPanelManager(this.orm, this.action);
                    await this._raytonPanel.init(projectId);
                    // Auto-open only on desktop — on mobile the user opens manually
                    if (this._raytonPanel._channelId && !window.matchMedia("(max-width: 768px)").matches) {
                        this._raytonPanel.togglePanel();
                    }
                }
            }
        });

        onWillUnmount(() => {
            if (this._raytonPanel) {
                this._raytonPanel.destroy();
                this._raytonPanel = null;
            }
        });
    },

    _isProjectTaskView() {
        return this.model?.config?.resModel === "project.task";
    },

    _getProjectId() {
        const ctx = this.model?.config?.context || {};
        return ctx.default_project_id || ctx.active_id || null;
    },
});

// ─── Patch ListController ────────────────────────────────────────────────────

patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.action = useService("action");
        this._raytonPanel = null;

        onMounted(async () => {
            if (this._isProjectTaskView()) {
                const projectId = this._getProjectId();
                if (projectId) {
                    this._raytonPanel = new RaytonPanelManager(this.orm, this.action);
                    await this._raytonPanel.init(projectId);
                    // Auto-open only on desktop — on mobile the user opens manually
                    if (this._raytonPanel._channelId && !window.matchMedia("(max-width: 768px)").matches) {
                        this._raytonPanel.togglePanel();
                    }
                }
            }
        });

        onWillUnmount(() => {
            if (this._raytonPanel) {
                this._raytonPanel.destroy();
                this._raytonPanel = null;
            }
        });
    },

    _isProjectTaskView() {
        return this.model?.config?.resModel === "project.task";
    },

    _getProjectId() {
        const ctx = this.model?.config?.context || {};
        return ctx.default_project_id || ctx.active_id || null;
    },
});
