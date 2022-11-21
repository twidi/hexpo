const show_positioned_sizes = false;
const refresh_map = true;
const refresh_players = true;

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
    players = document.querySelector('#players');
if (refresh_map) setInterval(async () => {
    const response = await fetch('/grid', {cache: 'no-cache'});
    if (response.ok) {
        const data = await response.text();
        grid.setAttribute('src', 'data:image/png;base64,' + data);
    }
}, 1000);
if (refresh_players) setInterval(async () => {
    const response = await fetch('/players', {cache: 'no-cache'});
    if (response.ok) {
        players.innerHTML = await response.text();
    }
}, 1000);
