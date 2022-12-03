const show_positioned_sizes = false;
const do_reload = document.body.getAttribute("data-reload") === "true";
const refresh_map = do_reload;
const refresh_players = do_reload;
const refresh_messages = do_reload;

if (show_positioned_sizes) {
    let log = '\n';
    document.querySelectorAll('.positioned').forEach((el) => {
        const boundingRect = el.getBoundingClientRect();
        log += `    '${el.id}': ((${boundingRect.left}, ${boundingRect.top}), (${boundingRect.right}, ${boundingRect.bottom})),\n`;
    });
    let grid_area = document.querySelector('#grid-area');
    grid_area.classList.add('debug');
    grid_area.innerHTML = log;
    console.log(log);
}

let grid = document.querySelector('#grid'),
    players = document.querySelector('#players'),
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
if (refresh_messages && messages_queue) {
    setInterval(async () => {
        const response = await fetch('/messages.partial', {cache: 'no-cache'});
        if (response.ok) {
            messages_queue.insertAdjacentHTML('beforeend', await response.text());
        }
    }, 1000);

    (function () {
        const animation_duration = 1000;
        const message_duration = 10000;
        const max_visible = 4;
        const gap = 20;
        const queue = document.querySelector('#messages-queue');
        const container = document.querySelector('#messages');
        const total_width = container.clientWidth;
        const message_width = (total_width - gap * (max_visible - 1)) / max_visible;
        const one_offset = message_width + gap;
        container.style.setProperty("--animation-duration", `${animation_duration}ms`);
        container.style.setProperty("--messages-width", `${total_width}px`);
        container.style.setProperty("--message-width", `${message_width}px`);
        let messages = [];

        function queue_message(text) {
          const message = document.createElement("div");
          message.textContent = text;
          message.classList.add("message");
          queue.appendChild(message);
        }

        function unqueue_message() {
          if (messages.length >= max_visible) { return; }
          const message = queue.querySelector('.message');
          if (!message) { return; }
          container.appendChild(message);
          messages.push(message);
          setTimeout(update_messages, 100);
          setTimeout(() => remove_message(message), message_duration + animation_duration);
        }

        setInterval(unqueue_message, animation_duration);

        function update_messages() {
          const nb_messages = messages.length;
          const used_width = nb_messages * message_width + (nb_messages - 1) * gap;
          const start = Math.max(0, (total_width - used_width) / 2);
          for (let index = 0; index < nb_messages; index++) {
            const message = messages[index];
            message.style.transform = `translateX(${start + index * one_offset}px)`;
            message.style.opacity = 1;
          }
        }

        function remove_message(message) {
          messages = messages.filter(n => n !== message);
          message.classList.add("message-removed");
          setTimeout(() => container.removeChild(message), animation_duration);
          update_messages();
        }
    })();

}
