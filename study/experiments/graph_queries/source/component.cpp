#define main old_k2_main
#include "k2.cpp"
#undef main
#include <numeric>
V component(const Problem&p){
 if(p.endpoint)return direct(p);
 std::vector<int>parent(p.w+p.n);std::iota(parent.begin(),parent.end(),0);
 auto find=[&](int i){while(parent[i]!=i){parent[i]=parent[parent[i]];i=parent[i];}return i;};
 for(int j=0;j<p.n;++j)for(int w:p.bycol[j])parent[find(w)]=find(p.w+j);
 std::vector<int>rootid(p.w+p.n,-1),group(p.n);int groups=0;
 for(int j=0;j<p.n;++j){int r=find(p.w+j);if(rootid[r]<0)rootid[r]=groups++;group[j]=rootid[r];}
 std::vector<std::vector<int>>previous(groups);V d(p.w,1),f(p.w,1),t(p.n,1),result(p.n);F H=1,R=0;
 for(int j=0;j<p.n;++j){int g=group[j];F D=0,ratio=1,lossR=0;
  for(int w:p.bycol[j]){if(p.a[w]==0)continue;if(p.a[w]==1){D+=(1-D)*p.b[w][j];ratio*=1-p.b[w][j];continue;}F oldF=f[w],drop=p.a[w]*d[w]*p.b[w][j]/oldF;d[w]*=1-p.b[w][j];f[w]=1-p.a[w]+p.a[w]*d[w];D+=(1-D)*drop;ratio*=f[w]/oldF;}
  for(int i:previous[g]){F next=1;for(int w:p.bycol[i]){if(p.a[w]==0)continue;if(p.a[w]==1)next/=1-p.b[w][i];else next*=(1-p.a[w]+p.a[w]*d[w]/(1-p.b[w][i]))/f[w];}F loss=t[i]-next;lossR+=loss;R-=loss;t[i]=next;}
  if(ratio<=0||!std::isfinite(ratio))return direct(p);
  result[j]=H*(lossR+D*(R+1));H*=ratio;t[j]=1/ratio;R+=t[j]-1;previous[g].push_back(j);
  if(!std::isfinite(result[j])||!std::isfinite(R))return direct(p);
 }
 return result;
}
int main(int argc,char**argv){
 if(argc<2)return 2;auto setup=std::chrono::steady_clock::now();Problem p=read(argv[1]);auto ready=std::chrono::steady_clock::now();double budget=argc>2?std::stod(argv[2]):.02;V result;volatile F checksum=0;uint64_t reps=0;auto start=std::chrono::steady_clock::now();double elapsed;
 do{result=component(p);if(!result.empty())checksum+=result[0];++reps;elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();}while(elapsed<budget);
 std::cout<<std::setprecision(21)<<"{\"method\":\"component\",\"seconds\":"<<elapsed/reps<<",\"repeats\":"<<reps<<",\"setup_seconds\":"<<std::chrono::duration<double>(ready-setup).count()<<",\"values\":[";for(size_t i=0;i<result.size();++i){if(i)std::cout<<",";std::cout<<result[i];}std::cout<<"]}\n";
}
