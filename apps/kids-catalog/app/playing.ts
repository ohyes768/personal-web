// 浏览器播放状态：同一时间只允许一个合集在播，并记住是从哪一处发起的。
// 播放器只在发起处展开（候选区 / 设备歌单表），避免同一合集出现两个播放器同时出声。
export type PlayingCollection = {folder: string; origin: "candidates" | "device"};
