import { redirect } from "next/navigation";

// 精简后首页直接落日报列表（原今日总览时间线已下线）
export default function Home() {
  redirect("/reports");
}
