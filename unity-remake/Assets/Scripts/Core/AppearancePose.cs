using System;
using System.IO;

namespace Ao.SourceContracts
{
    // Read-only projection from already aligned source state. No animation clock.
    public readonly struct AppearancePose
    {
        public readonly string Clip;
        public readonly float Phase;
        public readonly int Heading;
        public readonly bool RaisedSword;
        AppearancePose(string clip,float phase,int heading,bool sword=false)
        {Clip=clip;Phase=phase;Heading=heading;RaisedSword=sword;}
        public static AppearancePose Select(byte[] actor,int update)
        {
            if(actor==null||actor.Length!=112)throw new InvalidDataException("Invalid presentation actor");
            int heading=SourceInteger.Word(actor,38),animation=SourceInteger.Word(actor,54);
            if(heading!=0&&heading!=2&&heading!=4&&heading!=6)throw new InvalidDataException("Unknown presentation heading");
            if(animation==24||animation==25)
            {
                int image=SourceInteger.Word(actor,52);
                if(image<35||image>38)throw new InvalidDataException("Missing required pickup pose "+image);
                return new AppearancePose("pickup_"+image,0,heading,image==38);
            }
            if(animation<0||animation>=16)throw new InvalidDataException("Unmapped required animation "+animation);
            bool moving=(SourceInteger.Word(actor,6)&2)!=0;
            if(!moving)return new AppearancePose("idle",(update%80)/80f,heading);
            int cursor=SourceInteger.Word(actor,44),timer=SourceInteger.Word(actor,48);
            if(cursor%3!=0||cursor>9||timer>=10)throw new InvalidDataException("Invalid source gait phase");
            return new AppearancePose("walk",(cursor/3*10+timer)/40f,heading);
        }
    }
}
