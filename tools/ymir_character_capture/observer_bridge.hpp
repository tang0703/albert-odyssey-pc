#pragma once
#include <ymir/core/scheduler.hpp>
#include <ymir/hw/vdp/vdp_state.hpp>

// Called only by the generated, separately built VDP translation unit.
// All emulator references are const: this observer cannot write game/VDP RAM.
void AOCharacterBind(const ymir::core::Scheduler &, const ymir::vdp::VDPState &);
void AOCharacterObserve(const char *event, const ymir::core::Scheduler &,
                        const ymir::vdp::VDPState &, bool drawing,
                        uint32 commandAddress = UINT32_MAX);
