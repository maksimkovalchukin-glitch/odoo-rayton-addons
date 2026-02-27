/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
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

function formatDate(iso) {
    if (!iso) return "";
    try {
        return new Date(iso).toLocaleString("uk-UA", {
            day: "2-digit", month: "2-digit",
            hour: "2-digit", minute: "2-digit",
        });
    } catch { return ""; }
}

function stripHtml(html) {
    const d = document.createElement("div");
    d.innerHTML = html || "";
    return d.textContent || d.innerText || "";
}

// ─── Panel Manager (plain JS, no OWL - avoids template registration issues) ──

class RaytonPanelManager {
    constructor(orm, action) {
        this.orm = orm;
        this.action = action;
        this.panelWidth = 390;
        this._open = false;
        this._channelId = null;
        this._channelName = "";
        this._projectId = null;

        this._toggle = null;   // toggle button element
        this._panel = null;    // panel element
        this._messagesEl = null;
        this._inputEl = null;
        this._sendBtn = null;

        this._resizing = false;
        this._resizeStartX = 0;
        this._resizeStartW = 390;

        this._onMouseMove = this._onMouseMove.bind(this);
        this._onMouseUp = this._onMouseUp.bind(this);
        window.addEventListener("mousemove", this._onMouseMove);
        window.addEventListener("mouseup", this._onMouseUp);
    }

    async init(projectId) {
        this._projectId = projectId;
        if (!projectId) return;

        try {
            const [proj] = await this.orm.read(
                "project.project",
                [projectId],
                ["discuss_channel_id", "discuss_channel_name"]
            );
            if (!proj) return;
            this._channelId = proj.discuss_channel_id ? proj.discuss_channel_id[0] : null;
            this._channelName = proj.discuss_channel_name || "";
        } catch (e) {
            console.warn("[RaytonHub] Failed to load project channel info:", e);
        }

        this._mountDOM();
    }

    _mountDOM() {
        // Toggle button
        const toggle = document.createElement("button");
        toggle.className = "o_rayton_panel_toggle";
        toggle.title = "Обговорення проекту";
        toggle.innerHTML = `<span class="o_toggle_icon">💬</span><span>Чат</span>`;
        toggle.addEventListener("click", () => this.togglePanel());
        document.body.appendChild(toggle);
        this._toggle = toggle;

        // Panel
        const panel = document.createElement("div");
        panel.className = "o_rayton_discussion_panel";
        panel.innerHTML = this._buildPanelHTML();
        document.body.appendChild(panel);
        this._panel = panel;

        // Wire close button
        panel.querySelector(".o_rayton_panel_close")
            ?.addEventListener("click", () => this.togglePanel());

        // Wire resize
        const resizeHandle = panel.querySelector(".o_rayton_panel_resize");
        resizeHandle?.addEventListener("mousedown", (e) => {
            this._resizing = true;
            this._resizeStartX = e.clientX;
            this._resizeStartW = this.panelWidth;
            resizeHandle.classList.add("resizing");
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

        // Wire settings link
        panel.querySelector(".o_rayton_settings_link")
            ?.addEventListener("click", (e) => {
                e.preventDefault();
                this._openProjectSettings();
            });
    }

    _buildPanelHTML() {
        const ch = this._channelId;
        const chName = this._channelName;

        const bodyContent = ch
            ? `
            <div class="o_rayton_messages"></div>
            <div class="o_rayton_composer">
                <textarea class="o_rayton_composer_input"
                    placeholder="Написати повідомлення... (Enter — надіслати)"
                    rows="1"></textarea>
                <button class="o_rayton_send_btn" title="Надіслати">➤</button>
            </div>`
            : `<div class="o_rayton_empty">
                <i class="fa fa-comments-o" style="font-size:44px;opacity:0.3;"></i>
                <p>До цього проекту не прив'язано канал.<br/>
                   <a href="#" class="o_rayton_settings_link">Налаштувати проект</a></p>
               </div>`;

        return `
            <div class="o_rayton_panel_resize"></div>
            <div class="o_rayton_panel_header">
                <div class="o_rayton_panel_header_info">
                    <div class="o_rayton_panel_header_title">💬 Обговорення проекту</div>
                    ${chName ? `<div class="o_rayton_panel_header_sub"># ${chName}</div>` : ""}
                </div>
                <button class="o_rayton_panel_close" title="Закрити">✕</button>
            </div>
            <div class="o_rayton_panel_body">${bodyContent}</div>
        `;
    }

    togglePanel() {
        this._open = !this._open;

        if (this._open) {
            this._panel?.classList.add("open");
            if (this._toggle) {
                this._toggle.innerHTML = `<span class="o_toggle_icon">❮</span>`;
            }
            this._shiftContent(true);
            if (this._channelId) this._loadMessages();
        } else {
            this._panel?.classList.remove("open");
            if (this._toggle) {
                this._toggle.innerHTML = `<span class="o_toggle_icon">💬</span><span>Чат</span>`;
            }
            this._shiftContent(false);
        }
    }

    _shiftContent(open) {
        const el = document.querySelector(".o_action_manager > .o_action");
        if (!el) return;
        el.style.transition = "margin-right 0.32s cubic-bezier(0.4, 0, 0.2, 1)";
        el.style.marginRight = open ? this.panelWidth + "px" : "0px";
    }

    async _loadMessages() {
        if (!this._channelId || !this._messagesEl) return;
        this._messagesEl.innerHTML = `
            <div class="o_rayton_loading">
                <div class="o_rayton_spinner"></div>
                <span>Завантаження...</span>
            </div>`;

        try {
            const messages = await this.orm.searchRead(
                "mail.message",
                [
                    ["res_id", "=", this._channelId],
                    ["model", "=", "discuss.channel"],
                    ["message_type", "in", ["comment", "email"]],
                ],
                ["author_id", "body", "date"],
                { limit: 60, order: "date asc" }
            );

            this._messagesEl.innerHTML = "";

            if (!messages.length) {
                this._messagesEl.innerHTML = `
                    <div class="o_rayton_empty">
                        <i class="fa fa-comment-o" style="font-size:36px;opacity:0.3;"></i>
                        <p>Повідомлень ще немає.<br/>Напишіть першим! 👋</p>
                    </div>`;
                return;
            }

            let lastDate = "";
            messages.forEach(msg => {
                const d = msg.date ? new Date(msg.date) : null;
                const dateLabel = d
                    ? d.toLocaleDateString("uk-UA", { day: "2-digit", month: "long", year: "numeric" })
                    : "";

                if (dateLabel && dateLabel !== lastDate) {
                    lastDate = dateLabel;
                    const div = document.createElement("div");
                    div.className = "o_rayton_date_divider";
                    div.textContent = dateLabel;
                    this._messagesEl.appendChild(div);
                }

                const author = msg.author_id ? msg.author_id[1] : "Невідомий";
                const initials = getInitials(author);
                const time = formatDate(msg.date);
                const body = stripHtml(msg.body);

                const el = document.createElement("div");
                el.className = "o_rayton_message";
                el.innerHTML = `
                    <div class="o_rayton_avatar">${initials}</div>
                    <div class="o_rayton_msg_content">
                        <div class="o_rayton_msg_meta">
                            <span class="o_rayton_msg_author">${author}</span>
                            <span class="o_rayton_msg_time">${time}</span>
                        </div>
                        <div class="o_rayton_msg_body">${body}</div>
                    </div>`;
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
        window.removeEventListener("mousemove", this._onMouseMove);
        window.removeEventListener("mouseup", this._onMouseUp);
        this._shiftContent(false);
        this._toggle?.remove();
        this._panel?.remove();
    }
}

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
        return (
            this.model?.config?.resModel === "project.task"
        );
    },

    _getProjectId() {
        const ctx = this.model?.config?.context || {};
        return ctx.default_project_id || ctx.active_id || null;
    },
});
