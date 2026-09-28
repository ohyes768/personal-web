const backend=process.env.KIDS_BACKEND_URL||"http://localhost:8098";
const nextConfig={output:"standalone",basePath:"/kids",async rewrites(){
  return[{source:"/api/kids/:path*",destination:`${backend}/api/:path*`,basePath:false}];
}};export default nextConfig;
