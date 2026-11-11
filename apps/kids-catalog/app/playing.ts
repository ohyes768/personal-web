// 底部悬浮播放条的状态：当前播放的合集（目录名 + 展示标题）。
// 播放条是页面级单例：候选清单与「当前设备歌单」表共用这一份状态，
// 同一时刻只会有一个播放器实例。
export type PlayingCollection = {folder: string; title: string};
