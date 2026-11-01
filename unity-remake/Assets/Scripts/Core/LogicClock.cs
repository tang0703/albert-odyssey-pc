using System;
namespace Ao.SourceContracts
{
    public sealed class LogicClock
    {
        public const double TickSeconds=176473.0/10546875.0;
        double remainder;
        public void Push(double seconds)
        {if(double.IsNaN(seconds)||double.IsInfinity(seconds)||seconds<0)throw new ArgumentOutOfRangeException(nameof(seconds));remainder+=seconds;}
        public bool Take(){if(remainder<TickSeconds)return false;remainder-=TickSeconds;return true;}
        public void Clear(){remainder=0;}
    }
}
