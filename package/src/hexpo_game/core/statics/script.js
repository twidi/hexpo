const show_positioned_sizes = false;
const do_reload = document.body.getAttribute("data-reload") === "true";
const refresh_map = do_reload;
const refresh_players = do_reload;
const refresh_step = do_reload;
const refresh_messages = do_reload;

if (show_positioned_sizes) {
    let log = '\n';
    document.querySelectorAll('.positioned').forEach((el) => {
        const boundingRect = el.getBoundingClientRect();
        log += `    '${el.id}': ((${Math.round(boundingRect.left)}, ${Math.round(boundingRect.top)}), (${Math.round(boundingRect.right)}, ${Math.round(boundingRect.bottom)})),\n`;
    });
    let grid_area = document.querySelector('#grid-area');
    grid_area.classList.add('debug');
    grid_area.innerHTML = log;
    console.log(log);
}

let grid = document.querySelector('#grid'),
    players = document.querySelector('#players'),
    turn_step = document.querySelector('#turn-step'),
    step_instructions = document.querySelector('#step-instructions'),
    messages_queue = document.querySelector('#messages-queue');
if (refresh_map && grid) setInterval(async () => {
    const response = await fetch('/grid.raw', {cache: 'no-cache'});
    if (response.ok) {
        const data = await response.text();
        grid.setAttribute('src', 'data:image/png;base64,' + data);
    }
}, 1000);

if (refresh_players && players) setInterval(async () => {
    const response = await fetch('/players.partial', {cache: 'no-cache'});
    if (response.ok) {
        players.innerHTML = await response.text();
    }
}, 1000);

if (refresh_step && turn_step) {
    let step_fragment_holder = document.createElement("template");
    setInterval(async () => {
        const response = await fetch('/step.partial', {cache: 'no-cache'});
        if (response.ok) {
            step_fragment_holder.innerHTML = await response.text();
            const step_fragment = step_fragment_holder.content.querySelector('#turn-step-fragment');
            turn_step.innerHTML = step_fragment.innerHTML;
            if (step_instructions) {
                step_instructions.innerHTML = step_fragment_holder.content.querySelector('#step-instructions-fragment').innerHTML;
            }
            document.body.setAttribute('data-game-step', step_fragment.getAttribute('data-game-step'));
        }
    }, 500);
}


if (refresh_messages && messages_queue) {
    (function () {
        const message_delay = parseInt(document.body.getAttribute("data-message-delay"));
        const animation_duration = 1000;
        const max_visible = 4;
        const message_duration = max_visible * message_delay;
        const gap = 20;
        const container = document.querySelector('#messages');
        const total_width = container.clientWidth;
        const message_width = (total_width - gap * (max_visible - 1)) / max_visible;
        const one_offset = message_width + gap;
        container.style.setProperty("--animation-duration", `${animation_duration}ms`);
        container.style.setProperty("--messages-gap", `${gap}px`);
        container.style.setProperty("--messages-width", `${total_width}px`);
        container.style.setProperty("--message-width", `${message_width}px`);
        let last_displayed_at = null;
        let messages = [];
        let nb_displayed = 0;

        async function fetch_messages() {
            const response = await fetch('/messages.partial', {cache: 'no-cache'});
            if (response.ok) {
                messages_queue.insertAdjacentHTML('beforeend', await response.text());
            }
            messages_queue.querySelectorAll('.message').forEach((el) => {
                container.appendChild(el);
                messages.push({element: el, position: null, displayed_at: null});
            });
        }
        setInterval(fetch_messages, 500);

        function update_messages() {
            let messages_to_delete = [];
            const now = Date.now();
            for (let message of messages) {
                if (message.displayed_at !== null && (now - message.displayed_at) > message_duration) {
                    messages_to_delete.push(message);
                }
            }
            for (let message of messages_to_delete) {
                messages = messages.filter(n => n !== message);
                message.element.classList.add("message-removed");
                setTimeout(() => container.removeChild(message.element), animation_duration);
                nb_displayed--;
            }
            const used_width = nb_displayed * message_width + (nb_displayed - 1) * gap;
            const start = Math.max(0, (total_width - used_width) / 2);
            for (let message of messages) {
                if (message.displayed_at === null) {
                    if (last_displayed_at !== null && (now - last_displayed_at) < message_delay) {
                        break
                    }
                    message.element.style.opacity = '1';
                    message.displayed_at = now;
                    last_displayed_at = now;
                    nb_displayed++;
                }
            }
            for (let index = 0; index < messages.length; index++) {
                const message = messages[index];
                if (message.displayed_at === null) { break }
                const position = start + index * one_offset;
                if (message.position !== position) {
                    message.position = position;
                    message.element.style.transform = `translateX(${position}px)`;
                }
            }
        }
        setInterval(update_messages, 100);
    })();

}
