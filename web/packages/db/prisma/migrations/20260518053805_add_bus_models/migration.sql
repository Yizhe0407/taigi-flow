-- CreateTable
CREATE TABLE "BusOperator" (
    "id" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "nameZh" TEXT NOT NULL,
    "nameEn" TEXT NOT NULL,

    CONSTRAINT "BusOperator_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "BusRoute" (
    "uid" TEXT NOT NULL,
    "routeId" TEXT NOT NULL,
    "nameZh" TEXT NOT NULL,
    "nameEn" TEXT NOT NULL,
    "headsign" TEXT,
    "direction" INTEGER NOT NULL,
    "city" TEXT NOT NULL,
    "operatorId" TEXT NOT NULL,

    CONSTRAINT "BusRoute_pkey" PRIMARY KEY ("uid")
);

-- CreateTable
CREATE TABLE "BusStop" (
    "uid" TEXT NOT NULL,
    "stopId" TEXT NOT NULL,
    "nameZh" TEXT NOT NULL,
    "nameEn" TEXT NOT NULL,
    "lat" DOUBLE PRECISION NOT NULL,
    "lng" DOUBLE PRECISION NOT NULL,
    "address" TEXT,
    "city" TEXT NOT NULL,

    CONSTRAINT "BusStop_pkey" PRIMARY KEY ("uid")
);

-- CreateTable
CREATE TABLE "RouteStop" (
    "routeUid" TEXT NOT NULL,
    "stopUid" TEXT NOT NULL,
    "sequence" INTEGER NOT NULL,
    "boarding" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "RouteStop_pkey" PRIMARY KEY ("routeUid","stopUid","sequence")
);

-- CreateTable
CREATE TABLE "BusSchedule" (
    "id" TEXT NOT NULL,
    "routeUid" TEXT NOT NULL,
    "tripId" TEXT NOT NULL,
    "serviceDays" INTEGER NOT NULL,
    "isLowFloor" BOOLEAN NOT NULL DEFAULT false,
    "stopTimes" JSONB NOT NULL,

    CONSTRAINT "BusSchedule_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "BusRoute_city_idx" ON "BusRoute"("city");

-- CreateIndex
CREATE INDEX "BusRoute_nameZh_idx" ON "BusRoute"("nameZh");

-- CreateIndex
CREATE INDEX "BusStop_city_idx" ON "BusStop"("city");

-- CreateIndex
CREATE INDEX "BusStop_nameZh_idx" ON "BusStop"("nameZh");

-- CreateIndex
CREATE INDEX "RouteStop_routeUid_sequence_idx" ON "RouteStop"("routeUid", "sequence");

-- CreateIndex
CREATE INDEX "RouteStop_stopUid_idx" ON "RouteStop"("stopUid");

-- CreateIndex
CREATE INDEX "BusSchedule_routeUid_serviceDays_idx" ON "BusSchedule"("routeUid", "serviceDays");

-- AddForeignKey
ALTER TABLE "BusRoute" ADD CONSTRAINT "BusRoute_operatorId_fkey" FOREIGN KEY ("operatorId") REFERENCES "BusOperator"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RouteStop" ADD CONSTRAINT "RouteStop_routeUid_fkey" FOREIGN KEY ("routeUid") REFERENCES "BusRoute"("uid") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "RouteStop" ADD CONSTRAINT "RouteStop_stopUid_fkey" FOREIGN KEY ("stopUid") REFERENCES "BusStop"("uid") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "BusSchedule" ADD CONSTRAINT "BusSchedule_routeUid_fkey" FOREIGN KEY ("routeUid") REFERENCES "BusRoute"("uid") ON DELETE RESTRICT ON UPDATE CASCADE;
