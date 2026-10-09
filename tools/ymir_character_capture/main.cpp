// Local source-verification tool. Does not write to an emulator process or game input files.
#include <ymir/sys/saturn.hpp>
#include <ymir/media/loader/loader.hpp>
#include <ymir/debug/sh2_tracer_base.hpp>
#include <cereal/archives/portable_binary.hpp>
#include <serdes/cereal_savestate.hpp>
#include "observer_bridge.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string_view>
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>

namespace fs = std::filesystem;
using namespace ymir;
constexpr auto kRevision = "54fead6a0001d3e4b6741a8d095ee8342266c3dc";
struct Capture;
static Capture *activeCapture = nullptr;
static const core::Scheduler *observedScheduler = nullptr;
static const vdp::VDPState *observedVDP = nullptr;
void AOCharacterBind(const core::Scheduler &scheduler, const vdp::VDPState &vdp) {
    observedScheduler = &scheduler;
    observedVDP = &vdp;
}

static std::string Quote(const std::string &s) {
    std::string out = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { out += '\\'; out += c; }
        else if (c < 32) { out += fmt::format("\\u{:04x}", c); }
        else out += c;
    }
    return out + '"';
}
static uint64 Number(const std::string &s) {
    size_t consumed = 0;
    if (s.empty() || s.front() == '-') throw std::runtime_error("Expected nonnegative number");
    auto v = std::stoull(s, &consumed, 0);
    if (consumed != s.size()) throw std::runtime_error("Invalid number: " + s);
    return v;
}
static uint32 Address(const std::string &s) {
    auto n = Number(s);
    if (n > UINT32_MAX) throw std::runtime_error("Address exceeds 32 bits");
    return uint32(n);
}
static std::string HexBytes(const uint8 *p, size_t size) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string out(size * 2, '0');
    for (size_t i = 0; i < size; ++i) { out[i*2] = digits[p[i] >> 4]; out[i*2+1] = digits[p[i] & 15]; }
    return out;
}
static std::string SHA256(const uint8 *bytes, uint32 size) {
    struct Provider {
        BCRYPT_ALG_HANDLE handle{};
        Provider() {
            if (BCryptOpenAlgorithmProvider(&handle,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0)
                throw std::runtime_error("SHA256 provider unavailable");
        }
        ~Provider() { BCryptCloseAlgorithmProvider(handle,0); }
    };
    static Provider provider;
    std::array<uint8,32> digest{};
    if (BCryptHash(provider.handle,nullptr,0,const_cast<uint8 *>(bytes),size,digest.data(),ULONG(digest.size()))<0)
        throw std::runtime_error("SHA256 hashing failed");
    return HexBytes(digest.data(),digest.size());
}
template<typename T> static void WriteBytes(const fs::path &p, const T &v) {
    std::ofstream out(p, std::ios::binary);
    out.exceptions(std::ios::failbit | std::ios::badbit);
    out.write(reinterpret_cast<const char *>(v.data()), std::streamsize(v.size() * sizeof(v[0])));
}
struct Range { uint32 address; uint32 size; };
struct Options {
    fs::path ipl, disc, loadState, sequence, output;
    uint32 sampleEvery = 1;
    uint32 traceFunction = 0;
    std::set<uint32> hooks;
    std::vector<Range> watches;
};
struct Input { std::string name; uint16 pressed; uint32 frames; };
static uint16 ButtonMask(const std::string &s) {
    using B = peripheral::Button;
    const std::map<std::string, B> buttons{{"none",B::None},{"up",B::Up},{"down",B::Down},
        {"left",B::Left},{"right",B::Right},{"start",B::Start},{"a",B::A},{"b",B::B},{"c",B::C}};
    auto it = buttons.find(s);
    if (it == buttons.end()) throw std::runtime_error("Unknown single input: " + s);
    return uint16(it->second);
}
static Options Parse(int argc, char **argv) {
    Options o;
    for (int i = 1; i < argc; ++i) {
        std::string key = argv[i];
        if (i+1 == argc) throw std::runtime_error("Missing argument for " + key);
        std::string value = argv[++i];
        if (key == "--ipl") o.ipl = fs::u8path(value);
        else if (key == "--disc") o.disc = fs::u8path(value);
        else if (key == "--load-state") o.loadState = fs::u8path(value);
        else if (key == "--sequence") o.sequence = fs::u8path(value);
        else if (key == "--output") o.output = fs::u8path(value);
        else if (key == "--sample-every") o.sampleEvery = Address(value);
        else if (key == "--hook-pc") o.hooks.insert(Address(value));
        else if (key == "--trace-function") o.traceFunction = Address(value);
        else if (key == "--watch-range") {
            auto colon = value.find(':');
            if (colon == std::string::npos) throw std::runtime_error("watch-range is address:length");
            o.watches.push_back({Address(value.substr(0,colon)), Address(value.substr(colon+1))});
        } else throw std::runtime_error("Unknown argument: " + key);
    }
    if (o.ipl.empty() || o.disc.empty() || o.sequence.empty() || o.output.empty() || !o.sampleEvery)
        throw std::runtime_error("Required: --ipl --disc --sequence --output; --sample-every must be positive");
    if (fs::exists(o.output)) throw std::runtime_error("Output must be a new directory; refusing to overwrite evidence");
    for (auto r : o.watches) {
        if (!r.size || r.size > 0x10000 || uint64(r.address)+r.size > UINT32_MAX)
            throw std::runtime_error("Invalid watch range");
        uint32 a = r.address & 0x1FFFFFFF;
        if (!((a >= 0x06000000 && uint64(a)+r.size <= 0x06100000) ||
              (a >= 0x00200000 && uint64(a)+r.size <= 0x00300000)))
            throw std::runtime_error("Only WRAM watch ranges are supported");
    }
    return o;
}
static std::vector<Input> ReadSequence(const fs::path &path) {
    std::ifstream file(path);
    if (!file) throw std::runtime_error("Cannot read sequence");
    std::vector<Input> inputs;
    std::string line;
    uint64 total = 0;
    while (std::getline(file,line)) {
        if (auto hash = line.find('#'); hash != std::string::npos) line.resize(hash);
        std::istringstream row(line);
        std::string name, count, extra;
        if (!(row >> name)) continue;
        if (!(row >> count) || (row >> extra)) throw std::runtime_error("Sequence rows: single_button frame_count");
        uint64 n = Number(count);
        if (!n || (total += n) > 1000000) throw std::runtime_error("Sequence outside 1..1000000 total frames");
        inputs.push_back({name,ButtonMask(name),uint32(n)});
    }
    if (inputs.empty()) throw std::runtime_error("Empty sequence");
    return inputs;
}
struct Capture : debug::ISH2Tracer {
    Options options;
    std::unique_ptr<Saturn> saturn = std::make_unique<Saturn>();
    std::unique_ptr<savestate::SaveState> state = std::make_unique<savestate::SaveState>();
    uint64 frame = 0, videoSerial = 0, inputPolls = 0, hookSerial = 0, updateSerial = 0;
    uint64 eventSerial = 0, fetchedCommands = 0, executedCommands = 0;
    bool observedDrawing = false;
    std::set<std::string> blobs;
    struct InvalidFetchRun {
        bool active=false;
        uint64 frame=0, firstEvent=0, repeatFirst=0, repeatLast=0, firstCount=0, lastCount=0, repeats=0;
        uint32 address=0;
        uint8 bank=0;
        std::vector<uint8> bytes;
    } invalidRun;
    uint16 pressed = 0;
    std::string input = "none";
    std::vector<uint32> pixels;
    uint32 width = 0, height = 0;
    std::ofstream hooks, frames, vdpEvents;
    struct Call { uint32 returnPC, actor; uint64 id; };
    std::vector<Call> calls;
    explicit Capture(Options o) : options(std::move(o)) {}
    uint64 Count() const {
        if (!observedScheduler) throw std::runtime_error("VDP observer clock was not bound");
        return observedScheduler->CurrentCount();
    }
    std::string Blob(const uint8 *data, uint32 length) {
        const auto hash = SHA256(data,length);
        if (blobs.insert(hash).second)
            WriteBytes(options.output/"blobs"/(hash+".bin"),std::span<const uint8>(data,length));
        return hash;
    }
    std::vector<uint8> VRAMSpan(uint32 address, uint32 length) const {
        std::vector<uint8> bytes(length);
        for (uint32 i=0; i<length; ++i) bytes[i]=observedVDP->mem1.VRAM[(address+i)&0x7FFFF];
        return bytes;
    }
    void PlayerJSON(std::ostream &out) const {
        // Identity is a runtime slot/address observation, not a character-name assertion.
        const auto slot=*Memory(0x060C27AE,1);
        const uint32 actor=0x060C8758+uint32(slot)*0x70;
        out << "\"player_slot\":" << unsigned(slot) << ",\"player_actor_address\":" << actor
            << ",\"player_actor_hex\":";
        if(slot<32) out << Quote(HexBytes(Memory(actor,0x70),0x70)); else out << "null";
    }
    void FlushInvalidFetch() {
        if(invalidRun.repeats) {
            vdpEvents << "{\"schema\":\"ao_ymir_vdp_event_v2\",\"kind\":\"command_fetch_repeat\",\"frame\":" << invalidRun.frame
                << ",\"scheduler_count\":" << invalidRun.firstCount << ",\"scheduler_count_last\":" << invalidRun.lastCount
                << ",\"event_index\":" << invalidRun.repeatFirst << ",\"event_index_last\":" << invalidRun.repeatLast
                << ",\"repeat_count\":" << invalidRun.repeats << ",\"repeats_event_index\":" << invalidRun.firstEvent
                << ",\"command_address\":" << invalidRun.address << ",\"command_hex\":" << Quote(HexBytes(invalidRun.bytes.data(),32))
                << ",\"display_bank\":" << unsigned(invalidRun.bank) << ",\"draw_bank\":" << unsigned(invalidRun.bank^1)
                << ",\"valid_opcode\":false,\"skip\":false,\"end\":false}\n";
        }
        invalidRun.active=false; invalidRun.repeats=0;
    }
    void VideoEvent(const char *kind, uint32 command=UINT32_MAX) {
        if (!activeCapture) return;
        const auto &s=*observedVDP;
        bool invalidFetch=false;
        std::vector<uint8> invalidBytes;
        if(std::string_view(kind)=="command_fetch") {
            ++fetchedCommands;
            invalidBytes=VRAMSpan(command,32);
            const uint16 ctrl=uint16((invalidBytes[0]<<8)|invalidBytes[1]);
            invalidFetch=(ctrl&0xC000)==0 && (ctrl&15)>0xB;
            if(invalidFetch && invalidRun.active && invalidRun.frame==frame && invalidRun.address==command
                && invalidRun.bank==s.displayFB && invalidRun.bytes==invalidBytes) {
                ++eventSerial;
                if(!invalidRun.repeats) {invalidRun.repeatFirst=eventSerial; invalidRun.firstCount=Count();}
                ++invalidRun.repeats; invalidRun.repeatLast=eventSerial; invalidRun.lastCount=Count();
                return;
            }
        }
        // A run never crosses another emitted event, hook, input frame, or changed command bytes/bank.
        FlushInvalidFetch();
        if(std::string_view(kind)=="vdp2_render_line") {
            vdpEvents << "{\"schema\":\"ao_ymir_vdp_event_v2\",\"frame\":" << frame
                << ",\"scheduler_count\":" << Count() << ",\"event_index\":" << ++eventSerial
                << ",\"kind\":\"vdp2_render_line\",\"line\":" << command
                << ",\"compose_video_serial\":" << videoSerial+1
                << ",\"display_bank\":" << unsigned(s.displayFB)
                << ",\"draw_bank\":" << unsigned(s.displayFB^1) << "}\n";
            return;
        }
        vdpEvents << "{\"schema\":\"ao_ymir_vdp_event_v2\",\"frame\":" << frame
            << ",\"scheduler_count\":" << Count() << ",\"event_index\":" << ++eventSerial
            << ",\"kind\":" << Quote(kind) << ",\"video_serial\":" << videoSerial
            << ",\"display_bank\":" << unsigned(s.displayFB) << ",\"draw_bank\":" << unsigned(s.displayFB^1)
            << ",\"drawing\":" << (observedDrawing?"true":"false")
            << ",\"framebuffer_width\":" << s.regs1.fbSizeH << ",\"framebuffer_height\":" << s.regs1.fbSizeV
            << ",\"hphase\":" << int(s.HPhase) << ",\"vphase\":" << int(s.VPhase)
            << ",\"VCNT\":" << s.regs2.VCNT << ",\"HCNT\":" << s.regs2.ReadHCNT()
            << ",\"master_pc\":" << saturn->masterSH2.GetProbe().PC()
            << ",\"current_command\":" << s.regs1.currCommandAddress
            << ",\"next_command\":" << s.regs1.nextCommandAddress
            << ",\"EDSR\":" << s.regs1.ReadEDSR() << ",\"COPR\":" << s.regs1.ReadCOPR()
            << ",\"LOPR\":" << s.regs1.ReadLOPR() << ",\"TVMR\":" << s.regs1.ReadTVMR()
            << ",\"FBCR\":" << s.regs1.ReadFBCR() << ",\"PTMR\":" << s.regs1.ReadPTMR() << ',';
        PlayerJSON(vdpEvents);
        // Raw register addresses 0x000..0x1FE; Read<true> suppresses read side effects.
        std::array<uint8,512> regs{};
        for (uint32 a=0; a<regs.size(); a+=2) {
            const auto value=s.regs2.Read<true>(a); regs[a]=uint8(value>>8); regs[a+1]=uint8(value);
        }
        vdpEvents << ",\"vdp2_registers_be_hex\":" << Quote(HexBytes(regs.data(),regs.size()))
            << ",\"cram_sha256\":" << Quote(Blob(s.mem2.CRAM.data(),uint32(s.mem2.CRAM.size())));
        if(command!=UINT32_MAX) {
            const auto bytes=VRAMSpan(command,32);
            const vdp::VDP1Command::Control control{.u16=uint16((bytes[0]<<8)|bytes[1])};
            vdpEvents << ",\"command_address\":" << command << ",\"command_hex\":" << Quote(HexBytes(bytes.data(),bytes.size()))
                << ",\"end\":" << (control.end?"true":"false")
                << ",\"skip\":" << (control.skip?"true":"false")
                << ",\"valid_opcode\":" << (control.IsValid()?"true":"false");
            if(std::string_view(kind)=="command_execute_before") {
                ++executedCommands;
                auto word=[&](unsigned offset){ return uint32((bytes[offset]<<8)|bytes[offset+1]); };
                const uint32 mode=(word(4)>>3)&7, opcode=word(0)&15;
                if(opcode<=3 && mode<=5) {
                    const uint32 w=((word(10)>>8)&63)*8, h=word(10)&255;
                    const uint32 length=mode<=1?w*h/2:mode<=4?w*h:w*h*2;
                    const uint32 address=word(8)*8;
                    const auto packed=VRAMSpan(address,length);
                    vdpEvents << ",\"texture\":{\"vram_address\":" << address << ",\"bytes\":" << length
                        << ",\"width\":" << w << ",\"height\":" << h << ",\"color_mode\":" << mode
                        << ",\"sha256\":" << Quote(Blob(packed.data(),uint32(packed.size()))) << '}';
                    if(mode==1) {
                        const auto lut=VRAMSpan(word(6)*8,32);
                        vdpEvents << ",\"lut\":{\"vram_address\":" << word(6)*8
                            << ",\"bytes\":32,\"sha256\":" << Quote(Blob(lut.data(),uint32(lut.size()))) << '}';
                    }
                }
                if(word(4)&4) {
                    const auto gouraud=VRAMSpan(word(28)*8,8);
                    vdpEvents << ",\"gouraud\":{\"vram_address\":" << word(28)*8
                        << ",\"bytes\":8,\"sha256\":" << Quote(Blob(gouraud.data(),uint32(gouraud.size()))) << '}';
                }
            }
        } else {
            vdpEvents << ",\"framebuffer_sha256\":["
                << Quote(SHA256(s.spriteFB[0].data(),uint32(s.spriteFB[0].size()))) << ','
                << Quote(SHA256(s.spriteFB[1].data(),uint32(s.spriteFB[1].size()))) << ']';
            if(std::string_view(kind)=="software_video_complete")
                vdpEvents << ",\"video_sha256\":" << Quote(SHA256(reinterpret_cast<const uint8 *>(pixels.data()),uint32(pixels.size()*4)));
        }
        vdpEvents << "}\n";
        if(invalidFetch) {
            invalidRun.active=true; invalidRun.frame=frame; invalidRun.firstEvent=eventSerial;
            invalidRun.address=command; invalidRun.bank=s.displayFB; invalidRun.bytes=std::move(invalidBytes);
        }
    }
    const uint8 *Memory(uint32 address, uint32 size) const {
        address &= 0x1FFFFFFF;
        if (address >= 0x06000000 && uint64(address)+size <= 0x06100000)
            return saturn->mem.WRAMHigh.data() + address - 0x06000000;
        if (address >= 0x00200000 && uint64(address)+size <= 0x00300000)
            return saturn->mem.WRAMLow.data() + address - 0x00200000;
        return nullptr;
    }
    void WatchJSON(std::ostream &out) const {
        out << "\"watches\":[";
        bool first = true;
        for (auto r : options.watches) {
            if (!first) out << ',';
            first = false;
            out << "{\"address\":" << r.address << ",\"bytes\":" << r.size << ",\"hex\":"
                << Quote(HexBytes(Memory(r.address,r.size),r.size)) << ",\"sha256\":"
                << Quote(SHA256(Memory(r.address,r.size),r.size)) << '}';
        }
        out << ']';
    }
    void Hook(const char *kind, uint32 pc, uint32 actor, uint64 update) {
        FlushInvalidFetch();
        const auto &p = saturn->masterSH2.GetProbe();
        hooks << "{\"frame\":" << frame << ",\"scheduler_count\":" << Count()
              << ",\"event_index\":" << ++eventSerial << ",\"hook_index\":" << ++hookSerial
              << ",\"function_call_index\":" << update << ",\"kind\":" << Quote(kind)
              << ",\"pc\":" << pc << ",\"pr\":" << p.PR() << ",\"input\":" << Quote(input)
              << ",\"input_polls\":" << inputPolls << ",\"r\":[";
        for (size_t i=0;i<16;++i) { if(i) hooks << ','; hooks << p.R(uint8(i)); }
        hooks << "],\"actor_address\":" << actor << ",\"actor_hex\":";
        if (auto *bytes = Memory(actor,0x70)) hooks << Quote(HexBytes(bytes,0x70)); else hooks << "null";
        hooks << ",\"flags_sha256\":" << Quote(SHA256(saturn->mem.WRAMLow.data()+0x10000,0x10000)) << ',';
        WatchJSON(hooks); hooks << "}\n";
    }
    void ExecuteInstruction(uint32 pc, uint16, bool delaySlot) override {
        // The tracer runs before the instruction; a function return is observed at
        // the captured PR after its RTS delay slot, never at a guessed exit opcode.
        if (!calls.empty() && !delaySlot && pc == calls.back().returnPC) {
            auto call = calls.back(); calls.pop_back(); Hook("return",pc,call.actor,call.id);
        }
        if (pc == options.traceFunction && options.traceFunction) {
            auto &p=saturn->masterSH2.GetProbe();
            calls.push_back({p.PR(),p.R(4),++updateSerial});
            Hook("entry",pc,p.R(4),updateSerial);
        }
        if (options.hooks.contains(pc)) {
            auto &p=saturn->masterSH2.GetProbe();
            Hook("pc",pc,p.R(4),calls.empty()?0:calls.back().id);
        }
    }
    void Save(const fs::path &path) {
        std::ofstream out(path,std::ios::binary);
        out.exceptions(std::ios::failbit|std::ios::badbit);
        cereal::PortableBinaryOutputArchive archive(out); archive(*state);
    }
    void Snapshot(bool saveState) {
        // At the initial boundary this also obtains the loaded controller drawing state.
        saturn->SaveState(*state);
        observedDrawing=state->vdp.vdp1State.drawing;
        VideoEvent("sample_boundary");
        const auto dir=options.output/fmt::format("frame-{:06}",frame);
        fs::create_directory(dir);
        WriteBytes(dir/"wram-high.bin",state->system.WRAMHigh);
        WriteBytes(dir/"wram-low.bin",state->system.WRAMLow);
        WriteBytes(dir/"vram1.bin",state->vdp.VRAM1);
        WriteBytes(dir/"vram2.bin",state->vdp.VRAM2);
        WriteBytes(dir/"cram.bin",state->vdp.CRAM);
        WriteBytes(dir/"vdp1-fb0.bin",state->vdp.spriteFB[0]);
        WriteBytes(dir/"vdp1-fb1.bin",state->vdp.spriteFB[1]);
        if (!pixels.empty()) {
            WriteBytes(dir/"video-rgba.bin",pixels);
            std::ofstream ppm(dir/"video.ppm",std::ios::binary);
            ppm.exceptions(std::ios::failbit|std::ios::badbit);
            ppm << "P6\n" << width << ' ' << height << "\n255\n";
            for (uint32 color:pixels) {
                char rgb[3]{char(color),char(color>>8),char(color>>16)};
                ppm.write(rgb,3);
            }
        }
        std::ofstream meta(dir/"sample.json");
        meta.exceptions(std::ios::failbit|std::ios::badbit);
        meta << "{\"schema\":\"ao_ymir_frame_sample_v2\",\"frame\":" << frame
             << ",\"boundary\":" << Quote(frame ? "after_RunFrame_return" : "initial_before_RunFrame")
             << ",\"event_index\":" << eventSerial
             << ",\"scheduler_count\":" << state->scheduler.currCount
             << ",\"video_serial\":" << videoSerial << ",\"video_width\":" << width
             << ",\"video_height\":" << height << ",\"input\":" << Quote(input)
             << ",\"input_polls\":" << inputPolls << ",\"function_calls\":" << updateSerial
             << ",\"flags_sha256\":" << Quote(SHA256(state->system.WRAMLow.data()+0x10000,0x10000))
             << ",\"master_pc\":" << state->msh2.PC << ",\"master_pr\":" << state->msh2.PR
             << ",\"master_r\":[";
        for (int i=0;i<16;++i) { if(i) meta << ','; meta << state->msh2.R[i]; }
        meta << "],\"vdp1\":{";
        const auto &r1=state->vdp.regs1;
#define AO_REG(name) meta << "\"" #name "\":" << r1.name << ',';
        AO_REG(TVMR) AO_REG(FBCR) AO_REG(PTMR) AO_REG(EWDR) AO_REG(EWLR) AO_REG(EWRR)
        AO_REG(EDSR) AO_REG(LOPR) AO_REG(COPR) AO_REG(MODR)
        AO_REG(eraseWriteValueLatch) AO_REG(eraseX1Latch) AO_REG(eraseY1Latch) AO_REG(eraseX3Latch) AO_REG(eraseY3Latch)
#undef AO_REG
        meta << "\"next_command\":" << r1.nextCommandAddress
             << ",\"display_bank\":" << unsigned(state->vdp.displayFB)
             << ",\"draw_bank\":" << unsigned(state->vdp.displayFB^1)
             << ",\"renderer_display_bank\":" << unsigned(state->vdp.renderer.displayFB)
             << ",\"drawing\":" << (state->vdp.vdp1State.drawing?"true":"false")
             << ",\"FBCRChanged\":" << (r1.FBCRChanged?"true":"false")
             << ",\"do_display_erase\":" << (state->vdp.vdp1State.doDisplayErase?"true":"false")
             << ",\"do_vblank_erase\":" << (state->vdp.vdp1State.doVBlankErase?"true":"false")
             << ",\"spillover_cycles\":" << state->vdp.vdp1State.spilloverCycles
             << ",\"timing_penalty\":" << state->vdp.vdp1State.timingPenalty
             << ",\"framebuffer_width\":" << observedVDP->regs1.fbSizeH
             << ",\"framebuffer_height\":" << observedVDP->regs1.fbSizeV
             << "},\"vdp2\":{";
        const auto &r2=state->vdp.regs2;
#define AO_REG(name) meta << "\"" #name "\":" << r2.name << ',';
#include "vdp2_register_names.inc"
#undef AO_REG
        meta << "\"displayEnabledLatch\":" << (r2.displayEnabledLatch?"true":"false")
             << ",\"borderColorModeLatch\":" << (r2.borderColorModeLatch?"true":"false")
             << ",\"VCNTLatch\":" << r2.VCNTLatch << "},";
        PlayerJSON(meta); meta << ',';
        WatchJSON(meta); meta << "}\n";
        if (saveState) Save(dir/"state.savestate");
    }
    void Run(const std::vector<Input> &sequence) {
        // All emulated processors and video rendering remain on this thread.
        auto &config=saturn->configuration;
        config.video.threadedVDP1=false; config.video.threadedVDP2=false; config.video.threadedDeinterlacer=false;
        config.audio.threadedSCSP=false;
        config.rtc.virtHardResetTimestamp=757382400; // 1994-01-01 UTC, fixed local capture default
        config.rtc.virtHardResetStrategy=core::config::rtc::HardResetStrategy::ResetToFixedTime;
        config.rtc.mode=core::config::rtc::Mode::Virtual;
        config.system.emulateSH2Cache=false;
        std::ifstream bios(options.ipl,std::ios::binary);
        std::vector<uint8> ipl((std::istreambuf_iterator<char>(bios)),{});
        if (ipl.size()!=sys::kIPLSize) throw std::runtime_error("IPL must be exactly 512 KiB");
        saturn->LoadIPL(std::span<uint8,sys::kIPLSize>(ipl.data(),sys::kIPLSize));
        media::Disc disc;
        if (!media::LoadDisc(options.disc,disc,false,[](media::MessageType t,std::string s) {
            if(t==media::MessageType::Error) std::cerr << s << '\n';
        })) throw std::runtime_error("Cannot load source disc");
        saturn->LoadDisc(std::move(disc));
        saturn->Reset(true);
        auto &port=saturn->SMPC.GetPeripheralPort1();
        port.SetPeripheralReportCallback({this,[](peripheral::PeripheralReport &report,void *ctx) {
            auto &self=*static_cast<Capture *>(ctx);
            ++self.inputPolls;
            report.report.controlPad.buttons=peripheral::Button(uint16(peripheral::Button::Default)&~self.pressed);
        }});
        port.ConnectControlPad();
        saturn->VDP.SetSoftwareRenderCallback({this,[](uint32 *fb,uint32 w,uint32 h,void *ctx) {
            auto &self=*static_cast<Capture *>(ctx);
            self.pixels.assign(fb,fb+size_t(w)*h); self.width=w; self.height=h; ++self.videoSerial;
            self.VideoEvent("software_video_complete");
        }});
        if (!options.loadState.empty()) {
            std::ifstream file(options.loadState,std::ios::binary);
            if(!file) throw std::runtime_error("Cannot open state");
            cereal::PortableBinaryInputArchive archive(file); archive(*state);
            if(file.peek()!=EOF) throw std::runtime_error("Trailing bytes after complete Ymir state");
            if(!saturn->LoadState(*state)) throw std::runtime_error("State rejected: format, BIOS/disc hash, or hardware mismatch");
        }
        if (options.traceFunction || !options.hooks.empty()) {
            saturn->EnableDebugTracing(true);
            saturn->masterSH2.UseTracer(this);
        }
        fs::create_directories(options.output);
        fs::create_directory(options.output/"blobs");
        hooks.open(options.output/"hooks.jsonl"); frames.open(options.output/"frames.jsonl");
        vdpEvents.open(options.output/"vdp-events.jsonl");
        vdpEvents.exceptions(std::ios::badbit|std::ios::failbit);
        hooks.exceptions(std::ios::badbit|std::ios::failbit); frames.exceptions(std::ios::badbit|std::ios::failbit);
        observedDrawing=state->vdp.vdp1State.drawing;
        activeCapture=this;
        auto &callbacks=saturn->VDP.GetRenderer().Callbacks;
        callbacks.VDP1FramebufferSwap={this,[](void *ctx){static_cast<Capture *>(ctx)->VideoEvent("public_vdp1_swap_before_flip");}};
        callbacks.VDP1DrawFinished={this,[](void *ctx){static_cast<Capture *>(ctx)->VideoEvent("public_vdp1_draw_finished");}};
        callbacks.VDP2DrawFinished={this,[](void *ctx){static_cast<Capture *>(ctx)->VideoEvent("public_vdp2_draw_finished");}};
        Snapshot(true);
        for(const auto &command:sequence) {
            pressed=command.pressed; input=command.name;
            for(uint32 n=0;n<command.frames;++n) {
                ++frame;
                uint64 prevVideo=videoSerial;
                saturn->RunFrame();
                if(videoSerial!=prevVideo+1) throw std::runtime_error("RunFrame must produce exactly one completed video frame");
                FlushInvalidFetch();
                frames << "{\"frame\":" << frame << ",\"input\":" << Quote(input)
                       << ",\"scheduler_count\":" << Count() << ",\"event_index\":" << ++eventSerial
                       << ",\"video_serial\":" << videoSerial << ",\"input_polls\":" << inputPolls
                       << ",\"function_calls\":" << updateSerial << ",\"wram_high_xxh128\":"
                       << Quote(ToString(CalcHash128(saturn->mem.WRAMHigh.data(),saturn->mem.WRAMHigh.size())))
                       << ","; WatchJSON(frames); frames << "}\n";
                if(frame%options.sampleEvery==0) Snapshot(false);
            }
        }
        // The terminal snapshot is always present, even between sample intervals.
        if(frame%options.sampleEvery!=0) Snapshot(true); else { saturn->SaveState(*state); Save(options.output/fmt::format("frame-{:06}",frame)/"state.savestate"); }
        FlushInvalidFetch(); hooks.flush(); frames.flush(); vdpEvents.flush();
        std::ofstream report(options.output/"capture.json");
        report.exceptions(std::ios::failbit|std::ios::badbit);
        report << "{\"schema\":\"ao_ymir_character_capture_v2\",\"ymir_revision\":" << Quote(kRevision)
               << ",\"status\":\"complete\",\"frames\":" << frame << ",\"video_serial\":" << videoSerial
               << ",\"function_calls\":" << updateSerial << ",\"pending_calls\":" << calls.size()
               << ",\"event_count\":" << eventSerial << ",\"fetched_commands\":" << fetchedCommands
               << ",\"executed_commands\":" << executedCommands << ",\"blob_count\":" << blobs.size()
               << ",\"ipl_hash_xxh128\":" << Quote(ToString(saturn->GetIPLHash()))
               << ",\"disc_hash_xxh128\":" << Quote(ToString(saturn->GetDiscHash()))
               << ",\"rtc\":\"virtual_fixed_1994_or_loaded_state\",\"render_threads\":0,\"sh2_cache\":false"
               << ",\"hook_boundary\":\"before_instruction; return uses entry PR after delay slot\"}\n";
        saturn->masterSH2.UseTracer(nullptr);
        activeCapture=nullptr;
        std::cout << "Captured " << frame << " frames, " << updateSerial << " function entries, " << hookSerial << " hooks\n";
    }
};
void AOCharacterObserve(const char *event, const core::Scheduler &, const vdp::VDPState &, bool drawing, uint32 command) {
    if (!activeCapture) return;
    activeCapture->observedDrawing=drawing;
    activeCapture->VideoEvent(event,command);
}
int main(int argc,char **argv) {
    if(argc==2 && std::string(argv[1])=="--help") {
        std::cout << "ao-ymir-character-capture --ipl BIOS --disc CUE --sequence INPUT.txt --output NEW_DIR [--load-state STATE] [--sample-every N] [--trace-function PC] [--hook-pc PC] [--watch-range ADDRESS:LENGTH]\n"
                  << "Input rows: none|up|down|left|right|start|a|b|c FRAME_COUNT. One RunFrame per count. Output never overwritten.\n";
        return 0;
    }
    try { auto options=Parse(argc,argv); auto sequence=ReadSequence(options.sequence); Capture capture(std::move(options)); capture.Run(sequence); return 0; }
    catch(const std::exception &e) { std::cerr << "CAPTURE FAILED: " << e.what() << '\n'; return 1; }
}
