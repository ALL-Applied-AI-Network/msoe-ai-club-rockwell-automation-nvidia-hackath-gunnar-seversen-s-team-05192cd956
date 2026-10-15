# Draft messages to organizers

Drafts for Gunnar to send. Nothing here has been sent. Edit freely.

## 1. Dr. Zeng (FANUC ER-4iA contact), Slack DM

> Hi Dr. Zeng, I'm Gunnar Seversen (team with Josh Cygan, Dataset 3 Grasping & Sorting). We're building on the ER-4iA cube-stacking twin and want to plan the physical test early. Three questions:
>
> 1. During a supervised test, how do planned motions reach the arm: the FANUC ROS 2 driver, a controller program loaded from exported waypoints (TP/LS), or something else? Our planner produces a joint-space trajectory and tool poses in the robot base frame, so we can export to whichever format you prefer.
> 2. The twin notes `sim_q3 = controller_J3 + J2` and UF0 330 mm above the base, UTOOL1 223 mm. Are those still the right controller conventions for the cell?
> 3. Is the installed gripper the SMC MHZL2-16D2 (as modeled) or a SCHUNK, and could we get the finger STEP files?
>
> Josh and I can come to CSI whenever suits you. Thanks!

## 2. `#compute-questions`

> Hi! Team Gunnar Seversen / Josh Cygan (Dataset 3). Two quick confirmations for the ER-4iA starter (`fanuc_er4ia_sim`):
>
> 1. **Cosmos setup:** we plan to use `transformers-cosmos3` from `github.com/nvidia/cosmos-framework` (`packages/transformers-cosmos3`, commit 7cfaf78) with `transformers==5.9.0`, and the public `nvidia/Cosmos3-Nano` weights from Hugging Face (revision e59a53c). Is that the intended setup, or is there a team-provided environment or weights mirror?
> 2. **Isaac Sim version:** the starter needs Isaac Sim **6.0** (the ER-4iA asset only ships with 6.0). Is the Brev Isaac launchable on 6.0, or 6.1? If not 6.0, we'll pip-install `isaacsim==6.0.0.1` on a plain L40S instance instead.
>
> Also, for the UWM DGX Sparks: which NVIDIA driver are they on? Isaac Sim 6.0 is reported to crash on Spark with the 595 driver and needs 580.x. Thanks!
