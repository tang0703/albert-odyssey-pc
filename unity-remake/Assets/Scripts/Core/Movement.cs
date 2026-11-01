using System;
using System.Collections.Generic;
using System.IO;
using static Ao.SourceContracts.SourceInteger;

namespace Ao.SourceContracts
{
    // Literal integer port of movement_core.gd. Called only with sealed source data.
    public static class Movement
    {
        public static readonly int[] Shape = {-192,-96,64,384,192};
        public static readonly int[] StraightSpeed = {8,16,24,32,40,48};
        private static readonly int[] DiagonalSpeed = {6,11,17,22,28,34};
        private static readonly int[] Directions = {255,6,2,255,4,5,3,255,0,7,1,255,255,255,255,255};
        public static byte[] Step(byte[] input,int pad,byte[] flags,HashSet<int> verified,out bool outside)
        {
            if(input.Length!=112 || (pad!=0 && pad!=0x1000 && pad!=0x2000 && pad!=0x4000 && pad!=0x8000))
                throw new InvalidDataException("Unsupported actor or movement input");
            if(input[41]!=1 || Word(input,8)!=9 || Word(input,38)>=8 || Word(input,36)!=3 ||
                (Word(input,6)&~(2|0x200))!=0x8180)
                throw new InvalidDataException("Unsupported controlled actor configuration");
            var next=(byte[])input.Clone();Gate(next,pad);
            if((Word(next,6)&2)!=0)Velocity(next);
            else PutWord(next,54,(Word(next,8)&1)!=0?Word(next,38):Word(next,38)>>1);
            PutWord(next,24,Word(next,24)+Word(next,30));PutWord(next,26,Word(next,26)+Word(next,32));
            PutWord(next,30,0);PutWord(next,32,0);
            var result=Collision(next,flags,verified,out outside);
            return outside?(byte[])input.Clone():result;
        }
        public static void Gate(byte[] actor, int pad)
        {
            PutWord(actor,6,Word(actor,6)&0xfffd); PutWord(actor,24,0); PutWord(actor,26,0);
            int direction=Directions[(pad>>12)&15];
            if(direction!=255){PutWord(actor,38,direction);PutWord(actor,6,Word(actor,6)|2);}
            PutWord(actor,36,3);
        }
        public static void Velocity(byte[] actor)
        {
            int speed=Word(actor,36), heading=Word(actor,38);
            if(speed>=StraightSpeed.Length || heading>=8) throw new InvalidDataException("Unsupported movement selector");
            int s=StraightSpeed[speed], d=DiagonalSpeed[speed];
            int[] x={s,d,0,-d,-s,-d,0,d},y={0,d,s,d,0,-d,-s,-d};
            PutWord(actor,24,x[heading]);PutWord(actor,26,y[heading]);
            PutWord(actor,54,(Word(actor,8)&1)!=0 ? 8+heading : 4+(heading>>1));
        }
        static int Sample(byte[] flags,int x,int y,HashSet<int> verified,ref bool outside)
        {
            int index=(y>>3)*256+(x>>3);
            if(index<0 || index>=flags.Length) throw new InvalidDataException("Source lookup exceeds captured flags");
            if(!verified.Contains(index)) outside=true;
            return flags[index];
        }
        static void Contact(byte[] a,int bit){a[75]|=(byte)bit;PutWord(a,6,Word(a,6)|0x200);}
        static void Slide(byte[] a,int offset,uint bitmap,int count,int correction)
        {
            if((bitmap&(1u<<count))==0) PutWord(a,offset,-correction);
            else if((bitmap&2)==0) PutWord(a,offset,correction);
        }
        public static byte[] Collision(byte[] input,byte[] flags,HashSet<int> verified,out bool outside)
        {
            var a=(byte[])input.Clone();outside=false;
            int selector=Word(a,10),mask=selector==0?0x80:0x40,modeMask=selector==0?0x20:0x10;
            a[72]=0;a[75]=0;PutWord(a,6,Word(a,6)&~0x200);
            int dx=Signed16(Word(a,24)),dy=Signed16(Word(a,26));bool bypass=(Word(a,6)&0x20)!=0;
            PutWord(a,0,Word(a,0)+dx);
            if(dx!=0 && !bypass)
            {
                int topRaw=Divide16(Signed16(Word(a,2))+Shape[1]);
                int top=topRaw&0x7ff,bottom=(topRaw+Divide16(Shape[4])-1)&0x7ff;
                bottom+=7-(bottom&7);
                int edge=Divide16(Signed16(Word(a,0))+Shape[0])&0x7ff;
                if(dx>0) edge=(edge+Divide16(Shape[3])-1)&65535;
                uint bitmap=0;int count=0,cursor=top;
                while(cursor<=bottom)
                {
                    cursor&=0x7ff;
                    int flag=Sample(flags,edge,cursor,verified,ref outside);
                    bitmap=unchecked((bitmap+((flag&mask)!=0?1u:0u))*2);
                    count++;cursor+=8;
                    if(count>256) throw new InvalidDataException("Unsupported wrapping scan");
                }
                if(Signed16((int)bitmap)!=0)
                {
                    int correction=(dx>0?(edge&7)+1:8-(edge&7))*16;
                    PutWord(a,0,(Word(a,0)+(dx>0?-correction:correction))&0xfff0);
                    Contact(a,dx>0?8:4);
                    if(dy==0) Slide(a,32,bitmap,count,correction);
                }
                else a[72]=(byte)(dx>0?8:4);
            }
            PutWord(a,2,Word(a,2)+dy);
            if(dy!=0 && !bypass)
            {
                int edge=Divide16(Signed16(Word(a,2))+Shape[1])&0x7ff;
                int left=Divide16(Signed16(Word(a,0))+Shape[0])&0x7ff;
                if(dy>0) edge+=Divide16(Shape[4])-1;
                int last=Divide16(Shape[3])>>3;if((left&7)==0)last--;
                uint bitmap=0;int count=0,cursor=left;
                for(int i=0;i<=last;i++)
                {
                    cursor&=0x7ff;
                    int flag=Sample(flags,cursor,edge,verified,ref outside);
                    bitmap=unchecked((bitmap+((flag&mask)!=0?1u:0u))*2);
                    count++;cursor+=8;
                }
                if(Signed16((int)bitmap)!=0)
                {
                    int correction=(dy>0?(edge&7)+1:8-(edge&7))*16;
                    PutWord(a,2,(Word(a,2)+(dy>0?-correction:correction))&0xfff0);
                    Contact(a,dy>0?2:1);
                    if(dx==0)Slide(a,30,bitmap,count,correction);
                }
                else a[72]=(byte)(dy>0?2:1);
            }
            int center=Sample(flags,(Signed16(Word(a,0))>>4)&0x7ff,(Signed16(Word(a,2))>>4)&0x7ff,verified,ref outside);
            if((Word(a,22)&0x10)!=0)PutWord(a,22,(Word(a,22)&0xff00)|((center&modeMask)!=0?0x13:0x12));
            if((center&8)!=0)PutWord(a,10,255);
            if((center&4)!=0)PutWord(a,10,0);
            a[74]=(byte)center;
            return a;
        }
    }
}
