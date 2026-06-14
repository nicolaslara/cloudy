"""Spatial cloud estimate — the cloud at *any* location from nearby stations.

The temporal models (Normals, damped) answer "how will the cloud here change?". This
package answers a different, complementary question: "what is the cloud at *my exact
point*, which isn't a station?" — replacing the product's honest cop-out ("nearest
station, 60 km away") with a real location estimate.

`statistical` serves the two live rungs (nearest station, then kNN of nearby
stations); `features` supplies them with the nearest-station ranking and the weekly
station-cloud history. A learned spatial model was trialled and dropped: on honest
station observations it did not beat the plain kNN average (see the Phase-B error
budget), so the cheap, explainable kNN is what we ship.
"""
