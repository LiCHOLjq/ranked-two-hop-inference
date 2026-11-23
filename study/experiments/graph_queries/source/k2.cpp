#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>
using F=long double;
using V=std::vector<F>;
std::string fallback_reason;
struct Problem {int w,n;V a;std::vector<V>b;std::vector<std::vector<int>> bycol;bool endpoint=false;uint64_t edges=0,pair_updates=0;};
Problem read(const std::string& file){
 std::ifstream in(file);Problem p;in>>p.w>>p.n;p.a.resize(p.w);for(auto &a:p.a)in>>a;p.b.assign(p.w,V(p.n));p.bycol.resize(p.n);
 for(int w=0;w<p.w;++w){uint64_t d=0;for(int j=0;j<p.n;++j){in>>p.b[w][j];if(p.b[w][j]>0){p.bycol[j].push_back(w);++d;}if(p.b[w][j]==1)p.endpoint=true;}p.edges+=d;p.pair_updates+=d*(d-1)/2;}
 return p;
}
V direct(const Problem&p){
 V nonzero(p.w,1),result(p.n);std::vector<int>zeros(p.w,0);F H=1,Z=0;
 for(int j=0;j<p.n;++j){
  for(int w:p.bycol[j]){F q=1-p.b[w][j];if(q==0)++zeros[w];else nonzero[w]*=q;}
  F nextH=1;for(int w=0;w<p.w;++w)nextH*=1-p.a[w]+p.a[w]*(zeros[w]?0:nonzero[w]);
  F nextZold=0;
  for(int i=0;i<j;++i){F term=1;for(int w=0;w<p.w;++w){F q=1-p.b[w][i],d;if(q==0)d=zeros[w]==1?nonzero[w]:0;else d=zeros[w]?0:nonzero[w]/q;term*=1-p.a[w]+p.a[w]*d;}nextZold+=term;}
  result[j]=Z-nextZold-F(j-1)*(H-nextH);Z=nextZold+H;H=nextH;
 }
 return result;
}
V sparse(const Problem&p){
 fallback_reason.clear();if(p.endpoint){fallback_reason="b_equals_one";return direct(p);}
 V d(p.w,1),f(p.w,1),t(p.n,1),result(p.n);std::vector<std::vector<int>>seen(p.w);F H=1,R=0;
 for(int j=0;j<p.n;++j){F D=0,ratio=1,lossR=0;
  for(int w:p.bycol[j]){
   F a=p.a[w],bj=p.b[w][j];if(a==0)continue;if(a==1){D+=(1-D)*bj;ratio*=1-bj;continue;}
   F oldD=d[w],newD=oldD*(1-bj),oldF=f[w],newF=1-a+a*newD;
   F drop=a*oldD*bj/oldF;D+=(1-D)*drop;ratio*=newF/oldF;
   for(int i:seen[w]){F bi=p.b[w][i];F frac=a*(1-a)*oldD*bi*bj/(((1-bi)*(1-a)+a*oldD)*newF);F loss=t[i]*frac;t[i]-=loss;R-=loss;lossR+=loss;}
   d[w]=newD;f[w]=newF;seen[w].push_back(j);
  }
  if(ratio<=0||!std::isfinite(ratio)){fallback_reason="unrepresentable_ratio";return direct(p);}
  result[j]=H*(lossR+D*(R+1));H*=ratio;t[j]=1/ratio;R+=t[j]-1;
  if(!std::isfinite(result[j])||!std::isfinite(R)){fallback_reason="nonfinite_state";return direct(p);}
 }
 return result;
}
V recompute(const Problem&p){
 if(p.endpoint)return direct(p);
 V d(p.w,1),f(p.w,1),t(p.n,1),result(p.n);F H=1,R=0;
 for(int j=0;j<p.n;++j){F D=0,ratio=1,lossR=0;
  for(int w:p.bycol[j]){if(p.a[w]==0)continue;if(p.a[w]==1){D+=(1-D)*p.b[w][j];ratio*=1-p.b[w][j];continue;}F oldF=f[w],drop=p.a[w]*d[w]*p.b[w][j]/oldF;d[w]*=1-p.b[w][j];f[w]=1-p.a[w]+p.a[w]*d[w];D+=(1-D)*drop;ratio*=f[w]/oldF;}
  F nextR=0;
  for(int i=0;i<j;++i){F next=1;for(int w:p.bycol[i]){if(p.a[w]==0)continue;if(p.a[w]==1)next/=1-p.b[w][i];else next*=(1-p.a[w]+p.a[w]*d[w]/(1-p.b[w][i]))/f[w];}lossR+=t[i]-next;t[i]=next;nextR+=next-1;}
  if(ratio<=0||!std::isfinite(ratio))return direct(p);
  R=nextR;result[j]=H*(lossR+D*(R+1));H*=ratio;t[j]=1/ratio;R+=t[j]-1;if(!std::isfinite(result[j])||!std::isfinite(R))return direct(p);
 }
 return result;
}
V top1(const Problem&p){
 V d(p.w,1),f(p.w,1),result(p.n);F H=1;
 for(int j=0;j<p.n;++j){F old=H;for(int w:p.bycol[j]){d[w]*=1-p.b[w][j];F next=1-p.a[w]+p.a[w]*d[w];if(f[w]>0)H*=next/f[w];else H=0;f[w]=next;}result[j]=old-H;}
 return result;
}
V enumeration(const Problem&p){
 if(p.w>18)throw std::runtime_error("enumeration >18 witnesses");V result(p.n);
 for(uint64_t mask=0;mask<(1ULL<<p.w);++mask){F weight=1;for(int w=0;w<p.w;++w)weight*=((mask>>w)&1)?p.a[w]:1-p.a[w];if(weight==0)continue;F c0=1,c1=0;
  for(int j=0;j<p.n;++j){F q=1;for(int w:p.bycol[j])if((mask>>w)&1)q*=1-p.b[w][j];F v=1-q;result[j]+=weight*v*(c0+c1);c1=c1*q+c0*v;c0*=q;}
 }
 return result;
}
V monte(const Problem&p,uint64_t seed,uint64_t samples){
 std::mt19937_64 rng(seed);std::uniform_real_distribution<double>unif(0,1);V result(p.n);std::vector<int>degree(p.w);for(auto&c:p.bycol)for(int w:c)++degree[w];
 for(uint64_t sample=0;sample<samples;++sample){std::vector<int>A(p.w);for(int w=0;w<p.w;++w)A[w]=unif(rng)<p.a[w];F c0=1,c1=0;
  for(int j=0;j<p.n;++j){F q=1;for(int w:p.bycol[j])q*=1-(degree[w]>1?A[w]:p.a[w])*p.b[w][j];F v=1-q;result[j]+=v*(c0+c1);c1=c1*q+c0*v;c0*=q;}
 }
 for(auto &x:result)x/=samples;return result;
}
int main(int argc,char**argv){
 if(argc<3)return 2;auto setup=std::chrono::steady_clock::now();Problem p=read(argv[1]);auto ready=std::chrono::steady_clock::now();std::string method=argv[2];double budget=argc>3?std::stod(argv[3]):.02;uint64_t seed=argc>4?std::stoull(argv[4]):1,samples=argc>5?std::stoull(argv[5]):4096;
 auto call=[&](){if(method=="direct")return direct(p);if(method=="sparse")return sparse(p);if(method=="recompute")return recompute(p);if(method=="enumeration")return enumeration(p);if(method=="top1")return top1(p);if(method=="static_rb")return monte(p,seed,samples);throw std::runtime_error("method");};
 V result;volatile F checksum=0;uint64_t repeats=0;auto start=std::chrono::steady_clock::now();double elapsed;
 do {result=call();if(!result.empty())checksum+=result[0];++repeats;elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();}while(elapsed<budget);
 std::cout<<std::setprecision(21)<<"{\"method\":\""<<method<<"\",\"w\":"<<p.w<<",\"n\":"<<p.n<<",\"edges\":"<<p.edges<<",\"pair_updates\":"<<p.pair_updates<<",\"endpoint_fallback\":"<<(p.endpoint&&method=="sparse"?"true":"false")<<",\"fallback_reason\":\""<<fallback_reason<<"\",\"repeats\":"<<repeats<<",\"seconds\":"<<elapsed/repeats<<",\"setup_seconds\":"<<std::chrono::duration<double>(ready-setup).count()<<",\"values\":[";
 for(size_t i=0;i<result.size();++i){if(i)std::cout<<",";std::cout<<result[i];}std::cout<<"]}\n";
}
